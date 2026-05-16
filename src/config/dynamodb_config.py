"""DynamoDB resource + table name configuration."""

import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")

BIN_TABLE_NAME = os.environ.get("BIN_TABLE_NAME", "BIN_Table")
SCHEME_CONFIG_TABLE_NAME = os.environ.get("SCHEME_CONFIG_TABLE_NAME", "Scheme_Config")
AUTH_RATE_STATS_TABLE_NAME = os.environ.get("AUTH_RATE_STATS_TABLE_NAME", "Auth_Rate_Stats")

_dynamodb_resource = None


def get_dynamodb_resource():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name=REGION)
    return _dynamodb_resource
