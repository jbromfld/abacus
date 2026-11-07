import httpx
import pytest
from abacus import local_model


def test_chat_transport_is_loopback_only_and_has_no_tools(monkeypatch):
    captured={}
    monkeypatch.setattr(local_model,'available_models',lambda:['test-local'])
    real_client=httpx.Client
    def handler(request):
        import json
        captured['url']=str(request.url);captured['body']=json.loads(request.content)
        return httpx.Response(200,text='{"message":{"content":"Budget "},"done":false}\n{"message":{"content":"answer"},"done":true}\n')
    def client(**kwargs):
        captured['client']=kwargs
        return real_client(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(local_model.httpx,'Client',client)
    messages=[{'role':'system','content':'Budget snapshot'},{'role':'user','content':'Question'}]
    assert local_model.chat_with_model('test-local',messages)=='Budget answer'
    assert captured['url']=='http://127.0.0.1:11434/api/chat'
    assert captured['client']['trust_env'] is False
    assert captured['client']['follow_redirects'] is False
    assert captured['body']['stream'] is True
    assert captured['client']['timeout'].read==300
    assert captured['client']['timeout'].connect==5
    assert captured['body']['think'] is False
    assert captured['body']['messages']==messages
    assert 'tools' not in captured['body']
    assert captured['body']['options']['num_predict']<=1000
    assert captured['body']['options']['num_ctx']==8192


def test_uninstalled_model_never_starts_chat(monkeypatch):
    monkeypatch.setattr(local_model,'available_models',lambda:['installed-model'])
    monkeypatch.setattr(local_model.httpx,'Client',lambda *a,**k:pytest.fail('Uninstalled model triggered chat'))
    with pytest.raises(ValueError,match='installed'):
        local_model.chat_with_model('not-installed',[])


def test_model_discovery_filters_cloud_models(monkeypatch):
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url):return httpx.Response(200,json={'models':[
            {'name':'local:3b'}, {'name':'remote:cloud'},
            {'name':'remote-other','remote_host':'https://example.invalid'},
            {'name':'remote-alias','remote_model':'remote'},
        ]},request=httpx.Request('GET',url))
    monkeypatch.setattr(local_model.httpx,'Client',Client)
    assert local_model.available_models()==['local:3b']


@pytest.mark.parametrize('payload,match', [
    ('{"message":{"content":"partial"},"done":false}\n', 'stopped before finishing'),
    ('{"message":{"content":""},"done":true}\n', 'empty reply'),
    ('{"error":"model crashed"}\n', 'could not complete'),
    ('{"message":{"content":12},"done":true}\n', 'invalid reply'),
])
def test_stream_failures_do_not_return_partial_advice(monkeypatch,payload,match):
    monkeypatch.setattr(local_model,'available_models',lambda:['local'])
    real_client=httpx.Client
    monkeypatch.setattr(local_model.httpx,'Client',lambda **kw:real_client(
        transport=httpx.MockTransport(lambda request:httpx.Response(200,text=payload)),**kw))
    with pytest.raises(ValueError,match=match):
        local_model.chat_with_model('local',[])


def test_stream_timeout_discards_partial_reply(monkeypatch):
    monkeypatch.setattr(local_model,'available_models',lambda:['local'])
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"message":{"content":"partial"},"done":false}\n'
            raise httpx.ReadTimeout('stalled')
    real_client=httpx.Client
    monkeypatch.setattr(local_model.httpx,'Client',lambda **kw:real_client(
        transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Interrupted())),**kw))
    with pytest.raises(httpx.ReadTimeout):
        local_model.chat_with_model('local',[])


def test_configured_timeout_and_total_generation_limit(monkeypatch):
    monkeypatch.setattr(local_model,'available_models',lambda:['local'])
    monkeypatch.setattr(local_model,'local_config',lambda:{'ADVISOR_TIMEOUT_SECONDS':'600'})
    real_client=httpx.Client
    def client(**kw):
        assert kw['timeout'].read==600
        return real_client(transport=httpx.MockTransport(lambda request:httpx.Response(200,
            text='{"message":{"content":"answer"},"done":true}\n')),**kw)
    monkeypatch.setattr(local_model.httpx,'Client',client)
    clock=iter([0,601])
    monkeypatch.setattr(local_model,'monotonic',lambda:next(clock))
    with pytest.raises(httpx.ReadTimeout,match='configured time limit'):
        local_model.chat_with_model('local',[])


@pytest.mark.parametrize('value',['no','10','1801','nan'])
def test_invalid_advisor_timeout(monkeypatch,value):
    monkeypatch.setattr(local_model,'available_models',lambda:['local'])
    monkeypatch.setattr(local_model,'local_config',lambda:{'ADVISOR_TIMEOUT_SECONDS':value})
    with pytest.raises(ValueError,match='ADVISOR_TIMEOUT_SECONDS'):
        local_model.chat_with_model('local',[])
