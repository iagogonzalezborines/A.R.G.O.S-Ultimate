"""Native Hermes plugin: the broker owns permissions, Hermes owns the turn."""
import json
import socket


def call(operation, args):
    try:
        with socket.socket(socket.AF_UNIX) as conn:
            conn.settimeout(5)
            conn.connect('/run/argos-broker.sock')
            conn.sendall(json.dumps({'op': operation, 'args': args}).encode() + b'\n')
            data = bytearray()
            while b'\n' not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    raise ConnectionError('Broker disconnected')
                data.extend(chunk)
                if len(data) > 131072:
                    raise ValueError('Oversized broker response')
            return data.decode().strip()
    except Exception as exc:
        return json.dumps({'error': type(exc).__name__, 'message': str(exc)})


def register(ctx):
    definitions = [
        ('argos_read', 'read', 'Read a bounded file in the disposable project.', {'path': {'type': 'string'}}),
        ('argos_propose', 'propose', 'Propose an exact change. This does not authorize or apply it.',
         {'path': {'type': 'string'}, 'content': {'type': 'string'}}),
        ('argos_apply', 'apply', 'Apply a proposal only if the external controller authorized its exact digest.',
         {'proposal_id': {'type': 'string'}, 'sha256': {'type': 'string'}}),
    ]
    for name, operation, description, properties in definitions:
        def handler(args, _op=operation, **kwargs):
            return call(_op, args)
        schema = {'name': name, 'description': description,
                  'parameters': {'type': 'object', 'properties': properties,
                                 'required': list(properties), 'additionalProperties': False}}
        def available():
            return json.loads(call('health', {})).get('ready') is True
        ctx.register_tool(name=name, toolset='argos_broker', schema=schema, handler=handler,
                          check_fn=available)
