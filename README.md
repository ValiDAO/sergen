# SerGen - Server Generator
SerGen allows to generate `~/.ssh/config`, `prometheus.yaml` and `/etc/ansible/hosts.ini`
from a single config YAML file.

## Installation

```
$ sudo apt install python3-pip
$ sudo pip3 install poetry
$ git clone git@github.com:ValiDAO/sergen.git
$ cd sergen && poetry install
```

## Usage

```
$ cd sergen && poetry run python sergen.py
```

## Sample servers.yaml file

```yaml
instances:

- name: validao-solana-m
  owner: validao
  server: hetzner-ax101-fi
  project: solana
  variables:
    flavour: mainnet
    keydir: validao-m
    ledger_dir: /home/solana/validator-ledger

servers:

- alias: hetzner-ax101-fi
  ip: 34.56.78.90
  key: /root/private-keys/key1_rsa
  user: solana
```
