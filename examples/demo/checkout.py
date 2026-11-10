"""Intentionally flawed teaching fixture. This file must never be executed."""

import sqlite3
import subprocess


def find_customer(name, connection):
    query = f"SELECT id, email FROM customers WHERE name = '{name}'"
    return connection.execute(query).fetchall()


def average_order_value(order_totals):
    return sum(order_totals) / len(order_totals)


def add_item(item, cart=[]):
    cart.append(item)
    return cart


def export_receipt(destination):
    return subprocess.run(f"cp receipt.txt {destination}", shell=True, check=True)


def open_store(path):
    return sqlite3.connect(path)
