import json
import os
import subprocess


def sync_bucket_uri(event: dict, context):
    """Syncs the content of s3 bucket URIs"""
    print(f"request: {json.dumps(event)}, context: {type(context)}")

    input_bucket_uri = os.environ["INPUT_BUCKET_URI"]
    output_bucket_uri = os.environ["OUTPUT_BUCKET_URI"]

    sync_command = f"/opt/awscli/aws s3 sync {input_bucket_uri} {output_bucket_uri}"
    subprocess.check_call(sync_command, shell=True)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": f"Successfully ran aws s3 sync {input_bucket_uri} {output_bucket_uri}\n",
    }
