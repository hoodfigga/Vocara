import json
import boto3
import time

dynamodb = boto3.resource('dynamodb')


table = dynamodb.Table('VocaraLicenses')

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        license_key = body.get('license_key')
        hwid = body.get('hwid')
        
        if not license_key or not hwid:
            return {'statusCode': 400, 'body': json.dumps({'valid': False, 'message': 'Missing parameters'})}
            
        response = table.get_item(Key={'LicenseKey': license_key})
        item = response.get('Item')
        
        if not item:
            return {'statusCode': 403, 'body': json.dumps({'valid': False, 'message': 'Invalid License Key'})}
            
        bound_hwid = item.get('HardwareID')
        
        if not bound_hwid or bound_hwid == "UNBOUND":
            table.update_item(
                Key={'LicenseKey': license_key},
                UpdateExpression="SET HardwareID = :h, ActivationTime = :t",
                ExpressionAttributeValues={
                    ':h': hwid,
                    ':t': int(time.time())
                }
            )
            return {'statusCode': 200, 'body': json.dumps({'valid': True, 'message': 'License activated successfully!'})}
            
        elif bound_hwid == hwid:
            return {'statusCode': 200, 'body': json.dumps({'valid': True, 'message': 'License verified.'})}
            
        else:
            return {'statusCode': 403, 'body': json.dumps({'valid': False, 'message': 'License is bound to another machine. Piracy detected.'})}

    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'valid': False, 'message': str(e)})}
