import argparse
import json
import os
import shutil
from datetime import datetime as dt
from datetime import timedelta

import boto3
from botocore.exceptions import ClientError

from progress_utils import ProgressPercentage

TIMEDELTA_BY_STORAGE_CLASS = {
    "STANDARD": timedelta(days=1),
    "STANDARD_IA": timedelta(days=30),
    "GLACIER": timedelta(days=30 * 3),
    "DEEP_ARCHIVE": timedelta(days=30 * 6)
}


def upload_file_to_s3(file_name, bucket, s3_client, object_name, storage_class="DEEP_ARCHIVE"):
    """
    Upload a file to an S3 bucket.
    Params:
        file_name: File to upload
        bucket: Bucket to upload to
        object_name: S3 object name. If not specified then file_name is used
    """

    # Upload the file
    try:
        print(f"Uploading {file_name} as s3://{bucket}/{object_name}")
        s3_client.upload_file(file_name, bucket, object_name,
                              ExtraArgs={'StorageClass': storage_class},
                              Callback=ProgressPercentage(file_name)
                              )
    except ClientError as e:
        print(e)


def upload_folder_as_zip(folder_path, bucket, s3_client, object_name, storage_class):
    """
    Save a folder as zip
    :param folder_path: path to zip
    :param bucket: bucket where to save backup
    :param s3_client: client to use for saving
    :param object_name: name to give to the backup file
    :param storage_class: storage class to save object to
    """
    output_path = os.path.join("temp", object_name)
    if not output_path.endswith(".zip"):
        output_path = output_path + ".zip"
    shutil.make_archive(output_path, 'zip', folder_path, verbose=True)

    upload_file_to_s3(output_path, bucket, s3_client, object_name, storage_class)
    os.remove(output_path)


def get_latest_modification_time(directory):
    """
    Find the latest modification time recursively in a folder
    :param directory: folder to date
    :return: the latest modification time in timestamp format (from os.path.getmtime)
    """
    latest_mod_time = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            mod_time = os.path.getmtime(file_path)
            if mod_time > latest_mod_time:
                latest_mod_time = mod_time
    return latest_mod_time


def execute_backup_from_config(bucket, object_config, s3_client):
    """
    Execute a backup from an object configuration
    :param bucket: the bucket where to save the backup
    :param object_config: the configuration, including path to save and storage class
    :param s3_client: the client to use
    """
    if object_config["StorageClass"] not in TIMEDELTA_BY_STORAGE_CLASS.keys():
        print(f"{object_config} requested storage class currently not allowed, skipping")
        return
    print(f"storing {object_config} to {bucket}")

    path = object_config["path"]
    if "objectName" not in object_config:
        if isinstance(path, list):
            print(f"ERROR, can't use list of paths without giving an object name")
            return
        object_name = path.replace("C:\\", "").replace("/", "_").replace("\\", "_")
        print(f"No object name chosen, using {object_name}")
    else:
        object_name = object_config["objectName"]

    last_upload = dt.fromtimestamp(0)
    try:
        metadata = s3_client.head_object(Bucket=bucket, Key=object_name)
        last_upload = metadata["LastModified"].replace(tzinfo=None)
        print(f"Found previous backup in date {last_upload}")
    except ClientError as e:
        if e.response["Error"]["Code"] == '404':
            print("Object not found, proceeding with first upload")
        else:
            raise e
    if isinstance(path, list):
        last_modified = min([dt.fromtimestamp(get_latest_modification_time(p)) for p in path])
    elif os.path.isdir(path):
        last_modified = dt.fromtimestamp(get_latest_modification_time(path))
    else:
        last_modified = dt.fromtimestamp(os.path.getmtime(path))
    print(f"Found latest changes in date {last_modified}")
    if last_modified > last_upload + TIMEDELTA_BY_STORAGE_CLASS[object_config.get("StorageClass", "DEEP_ARCHIVE")]:
        print(f"Latest change > last backup, proceeding to upload")
    elif object_config.get("force", False) and last_modified > last_upload:
        print("Latest upload too recent, but found command to force reload, proceeding to upload")
    else:
        print(f"Latest upload too recent, skipping. Force with force option in config")
        return
    if isinstance(path, list):
        print("ERROR list path not implemented yet")
        return
    elif os.path.isdir(path):
        upload_folder_as_zip(path, bucket, s3_client, object_name, object_config.get("StorageClass", "DEEP_ARCHIVE"))
    else:
        upload_file_to_s3(path, bucket, s3_client, object_name, object_config.get("StorageClass", "DEEP_ARCHIVE"))


def main():
    parser = argparse.ArgumentParser(
        prog='MyBackupS3',
        description='Stores backups to S3')
    parser.add_argument('--config-file', type=str,
                        help='config of the backups, it must contain an object formatted as the schema config-schema.json')

    bucket = os.environ.get("BUCKET")
    access_key, secret_key = os.environ.get("AWS_ACCESS_KEY"), os.environ.get("AWS_SECRET_KEY")

    s3_client = boto3.client(
        service_name='s3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )

    args = parser.parse_args()
    with open(args.config_file, "r", encoding='utf-8') as f:
        config = json.loads(" ".join(f.readlines()))
    for object_config in config["objects_to_store"]:
        execute_backup_from_config(bucket, object_config, s3_client)


if __name__ == "__main__":
    main()
