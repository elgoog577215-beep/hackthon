"""Opt-in local runtime affinity. This supplements, never replaces, authorization."""
import hashlib
import json
import os
from pathlib import Path

from starlette.responses import JSONResponse


def runtime_manifest():
    from knowledge_extract import CONTRACT
    data = os.path.normcase(os.path.abspath(os.getenv('LINGZHI_DATA_DIR') or 'data'))
    return {'runtime_id':os.getenv('LINGZHI_RUNTIME_ID',''),
        'release_sha':os.getenv('LINGZHI_RELEASE_SHA',''),
        'mode':os.getenv('LINGZHI_RUNTIME_MODE','unmanaged'),
        'data_id':hashlib.sha256(data.encode()).hexdigest()[:16],
        'knowledge_contract':CONTRACT}


def validate_frontend_bundle(directory):
    expected=runtime_manifest()
    if not expected['runtime_id']:return
    try: bundled=json.loads((Path(directory)/'runtime.json').read_text(encoding='utf8'))
    except (OSError,ValueError) as error:raise RuntimeError('Missing local runtime bundle manifest') from error
    if any(bundled.get(key)!=value for key,value in expected.items()):
        raise RuntimeError('Frontend/backend/data runtime identities do not match')


class RuntimeIdentityMiddleware:
    def __init__(self,app):
        self.app=app
        self.runtime_id=os.getenv('LINGZHI_RUNTIME_ID','')

    async def __call__(self,scope,receive,send):
        if (self.runtime_id and scope['type']=='http' and scope.get('path','').startswith('/api/')
                and scope.get('method') not in {'GET','HEAD','OPTIONS'}):
            supplied=dict(scope.get('headers',[])).get(b'x-lingzhi-runtime',b'').decode('latin1')
            if supplied!=self.runtime_id:
                await JSONResponse({'code':'RuntimeMismatch','detail':'页面与当前服务版本不匹配，请刷新页面后重试。'},
                    status_code=409)(scope,receive,send)
                return
        await self.app(scope,receive,send)
