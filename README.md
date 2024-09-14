# BackuS3

This is my personal script I use to backup my personal files to the cloud. This works uniquely with AWS.

To run it, you need to export three environment variables:

* BUCKET: the name of the S3 bucket to store the backups
* AWS_ACCESS_KEY: the access key of the credentials to send the backups
* AWS_SECRET_KEY: the secret key of the credentials.

Then you must run:

python main.py --config-file config.json

Where config.json is a file containing the specification on how what to backup and how and it is defined according to the schema provided in config-schema.json

