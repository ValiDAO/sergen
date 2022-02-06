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
