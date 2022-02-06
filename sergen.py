#!/usr/bin/env python

from collections import defaultdict
import importlib
import json
import pathlib
import subprocess
import sys

import yaml


NODES_PATH = "/root/nodes"
AUTOGEN_SECTION = "### AUTOGENERATED CONFIG ###"
SSH_CONFIG_PATH = "/root/.ssh/config"
ANSIBLE_INVENTORY_PATH = "/etc/ansible/hosts"
GRAFANA_DASHBOARDS_PATH = pathlib.Path("/var/lib/grafana-dashboards")
PROMETHEUS_PATH = "/root/prometheus.yml"


def _prepare_file(path):
    with open(path, "r") as config_file:
        result = config_file.read()
    autogen_begin = result.find(AUTOGEN_SECTION)
    if autogen_begin > 0:
        result = result[:autogen_begin-1]
    result += f"\n{AUTOGEN_SECTION}"
    return result


def _generate_grafana_dashboard(panels, owner):
    return {
        "annotations": {
            "list": []
        },
        "editable": False,
        "gnetId": None,
        "graphTooltip": 0,
        "links": [],
        "panels": panels,
        "schemaVersion": 30,
        "style": "dark",
        "tags": [],
        "templating": {
            "list": []
        },
        "time": {
            "from": "now-6h",
            "to": "now"
        },
        "timepicker": {},
        "timezone": "",
        "title": f"{owner} Dashboard",
        "uid": f"{owner}",
        "version": 1
    }


def _generate_grafana_transformations(config, project):
    transformations = {}
    for instance in config["instances"]:
        if instance["project"] != project:
            continue
        server_ip = config["servers"][instance["server"]]["ip"]
        assert server_ip not in transformations, f'{config["servers"][instance["server"]]["ip"]} is already in {transformations} for {project}'
        transformations[server_ip] = instance["name"]
    return {"transformations": [
        {
            "id": "renameByRegex",
            "options": {
                "regex": f".*{ip}.*",
                "renamePattern": name
            }
        } for ip, name in transformations.items()
    ]}



def regenerate_ssh_config(config):
    ssh_config = _prepare_file(SSH_CONFIG_PATH)
    for instance in config["instances"]:
        server = config["servers"][instance["server"]]
        ssh_config += f"""
Host {instance["name"]}
    User {server["user"]}
    HostName {server["ip"]}
    IdentityFile {server["key"]}

"""
    with open(SSH_CONFIG_PATH, "w") as ssh_config_file:
        ssh_config_file.write(ssh_config)


def regenerate_ansible_inventory(config):
    inventory = _prepare_file(ANSIBLE_INVENTORY_PATH)
    projects = sorted(set(instance["project"] for instance in config["instances"]))
    for project in projects:
        inventory += f"\n\n[{project}]"
        instances = [instance for instance in config["instances"] if instance["project"] == project]
        for instance in instances:
            inventory += f"\n{instance['name']} is_my_server={json.dumps(config['servers'][instance['server']].get('server-payee') is not None)}"
            all_variables = sorted(instance.get("variables", []))
            for var in all_variables:
                quote = '"' if (isinstance(instance['variables'][var], str) and ' ' in instance['variables'][var]) else ""
                inventory += f" {var}={quote}{instance['variables'][var]}{quote}"
        inventory += f'\n[{project}]'

    for owner in sorted(set(instance['owner'] for instance in config['instances'])):
        inventory += f"\n\n[{owner}]"
        instances = [instance for instance in config["instances"] if instance["owner"] == owner]
        for instance in instances:
            inventory += f"\n{instance['name']}"

    with open(ANSIBLE_INVENTORY_PATH, "w") as inventory_file:
        inventory_file.write(inventory)


def regenerate_prometheus_config(config):
    CONFIG_PREAMBLE = """# my global config
global:
  scrape_interval:     120s # Set the scrape interval to every 15 seconds. Default is every 1 minute.
  evaluation_interval: 120s # Evaluate rules every 15 seconds. The default is every 1 minute.
  # scrape_timeout is set to the global default (10s).

# Alertmanager configuration
alerting:
  alertmanagers:
  - static_configs:
    - targets:
      # - alertmanager:9093

# Load rules once and periodically evaluate them according to the global 'evaluation_interval'.
rule_files:
  # - "first_rules.yml"
  # - "second_rules.yml"

scrape_configs:
"""
    all_servers = ", ".join(f"'{server['ip']}:9977'" for server in config["servers"].values())
    SERVERS_HEALTHCHECKS = f"""
  - job_name: 'hosts'
    static_configs:
      - targets: [{all_servers}]
"""

    def generate_project_section(project_name, default_port):
        servers_to_query = ", ".join(set(
            f'\'{config["servers"][instance["server"]]["ip"]}:{default_port}\''
            for instance in config["instances"]
            if instance["project"] == project_name))
        return f"""
  - job_name: '{project_name}'
    static_configs:
      - targets: [{servers_to_query}]
"""

    with open(PROMETHEUS_PATH, "w") as prometeus_config:
        prometeus_config.write(CONFIG_PREAMBLE)
        prometeus_config.write(SERVERS_HEALTHCHECKS)
        # prometeus_config.write(generate_project_section('aleo', 9090))


sys.path.append(NODES_PATH)
def regenerate_grafana_dashboards(config):
    projects_by_user = defaultdict(set)
    all_projects = set()
    for instance in config["instances"]:
        projects_by_user[instance["owner"]].add(instance["project"])
        all_projects.add(instance["project"])

    for owner, projects in projects_by_user.items():
        row = 0
        panels = []
        for project in sorted(projects):
            if not (pathlib.Path(NODES_PATH) / project / "grafana_generator.py").exists():
                continue
            gen = importlib.import_module(f"{project}.grafana_generator")
            servers = [config["servers"][instance["server"]]["ip"]
                       for instance in config["instances"]
                       if instance["owner"] == owner and instance["project"] == project]
            new_panels = gen.generate_section(len(panels), row, servers=servers)
            if new_panels:
                row = max(p["gridPos"]["y"] + p["gridPos"]["h"] for p in new_panels)
                panels.extend(new_panels)
        dashboard = _generate_grafana_dashboard(panels, owner)
        with open(GRAFANA_DASHBOARDS_PATH / f"{owner}.json", "w") as dashboad_file:
            json.dump(dashboard, dashboad_file)

    row = 0
    panels = []
    for project in sorted(all_projects):
        if not (pathlib.Path(NODES_PATH) / project / "grafana_generator.py").exists():
            continue
        gen = importlib.import_module(f"{project}.grafana_generator")
        transformations = _generate_grafana_transformations(config, project)
        new_panels = gen.generate_section(len(panels), row, servers=None)  # admin
        if new_panels:
            for panel in new_panels:
                panel.update(transformations)
            row = max(p["gridPos"]["y"] + p["gridPos"]["h"] for p in new_panels)
            panels.extend(new_panels)
    admin_dashboard = _generate_grafana_dashboard(panels, "Admin")
    with open(GRAFANA_DASHBOARDS_PATH / "admin.json", "w") as dashboad_file:
        json.dump(admin_dashboard, dashboad_file)


def check_ssh_keys(config):
    for server in config["servers"].values():
        if "skip-ssh-check" in server:
            continue
        print(f"Checking SSH to {server}")
        subprocess.check_call(["ssh-copy-id", "-i", server["key"], f"{server['user']}@{server['ip']}"])


def main():
    with open("servers.yaml", "r") as config_file:
        config = yaml.full_load(config_file)
    config["servers"] = {server["alias"]: server for server in config["servers"]}
    regenerate_ssh_config(config)
    regenerate_ansible_inventory(config)
    regenerate_prometheus_config(config)
    regenerate_grafana_dashboards(config)
    check_ssh_keys(config)


if __name__ == "__main__":
    main()
