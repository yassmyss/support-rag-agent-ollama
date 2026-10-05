import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from ollama import ResponseError
from app import graph, main, rag, tools
from app.config import Settings
from app.sessions import SessionStore

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_sessions(monkeypatch):
    monkeypatch.setattr(main, 'sessions', SessionStore())


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.inputs = []
        self.bound = False
    def bind_tools(self, tool_list):
        assert {t.name for t in tool_list} == set(tools.TOOL_MAP)
        self.bound = True
        return self
    def invoke(self, messages):
        self.inputs.append(messages)
        return next(self.responses)


def call(name, args, id='t1'):
    return AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': id, 'type': 'tool_call'}])


@pytest.fixture
def knowledge(monkeypatch):
    docs = [Document(page_content='Comprueba el estado de WSL.', metadata={'source': 'docker.md'})]
    monkeypatch.setattr(rag, 'build_retriever', lambda: RunnableLambda(lambda _: docs))


def test_home_health_and_validation():
    assert client.get('/').status_code == 200
    assert 'Agente local' in client.get('/').text
    assert client.get('/health').json() == {'status': 'ok', 'provider': 'ollama'}
    for body in [{'question':'a'}, {'question':'   '}, {'question':'x'*2001},
                 {'question':'Docker', 'logs':'a'*12001}, {'question':'Docker', 'session_id':'bad'}]:
        assert client.post('/ask', json=body).status_code == 422


@pytest.mark.parametrize('error,code', [(httpx.ConnectError('offline'),503), (httpx.ReadTimeout('slow'),504), (ResponseError('missing',status_code=404),503)])
def test_dependency_errors(monkeypatch, error, code):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(main.support_graph, 'invoke', fail)
    response = client.post('/ask',json={'question':'Docker no inicia'})
    assert response.status_code == code
    assert isinstance(response.json()['detail'], str)
    assert len(main.sessions.sessions) == 0


def test_agent_chooses_tools_and_returns_sources(monkeypatch, knowledge):
    model = FakeModel([call('analyze_logs', {'log_text':'OOMKilled=true exited code 137'}),
                       call('read_procedure', {'source':'docker.md'}, 't2'),
                       AIMessage(content='Comprueba WSL y los límites de memoria según docker.md.')])
    monkeypatch.setattr(graph,'get_model',lambda:model)
    response = client.post('/ask',json={'question':'Docker se detiene', 'logs':'OOMKilled=true exited code 137'})
    assert response.status_code == 200
    data = response.json()
    assert data['category'] == 'containers'
    assert [t['tool'] for t in data['trace']] == ['search_knowledge','analyze_logs','read_procedure']
    assert all(t['status']=='ok' for t in data['trace'])
    assert data['sources'][0]['source'] == 'docker.md'
    assert 'Comprueba el estado de WSL.' in model.inputs[0][-1].content
    assert model.bound and not data['limit_reached']


def test_additional_search_and_escalation(monkeypatch, knowledge):
    model = FakeModel([call('search_knowledge',{'query':'incidencia permisos'}),
        call('prepare_escalation',{'summary':'Servicio no disponible','reason':'Sin permisos','impact':'multiple_users','checks':['Usuario confirma el fallo'],'missing_information':['Hora de inicio']},'t2'),
        AIMessage(content='He preparado un borrador para N2, pendiente de revisión.')])
    monkeypatch.setattr(graph,'get_model',lambda:model)
    data = client.post('/ask',json={'question':'No tengo permisos; afecta a varias personas'}).json()
    assert data['escalations'][0]['status'] == 'draft'
    assert data['escalations'][0]['priority'] == 'high'
    assert data['trace'][1]['origin'] == 'agent'


def test_conversation_and_delete(monkeypatch, knowledge):
    model = FakeModel([AIMessage(content='Comprueba WSL.'), AIMessage(content='Ahora recopila el error.')])
    monkeypatch.setattr(graph,'get_model',lambda:model)
    first = client.post('/ask',json={'question':'Docker no inicia'}).json()
    second = client.post('/ask',json={'question':'Ya lo comprobé; sigue fallando','session_id':first['session_id']})
    assert second.status_code == 200
    assert any(isinstance(m,HumanMessage) and m.content=='Docker no inicia' for m in model.inputs[1])
    assert client.delete('/sessions/'+first['session_id']).status_code == 204
    assert client.post('/ask',json={'question':'Continúa','session_id':first['session_id']}).status_code == 404


def test_loop_limit_and_unknown_tool(monkeypatch, knowledge):
    settings=Settings(_env_file=None,max_agent_rounds=1)
    monkeypatch.setattr(graph,'get_settings',lambda:settings)
    model=FakeModel([call('execute_shell',{'command':'rm files'}), AIMessage(content='No dispongo de esa herramienta.')])
    monkeypatch.setattr(graph,'get_model',lambda:model)
    data=client.post('/ask',json={'question':'Docker no inicia'}).json()
    assert data['limit_reached']
    assert data['trace'][-1]['status']=='error'
    assert len(model.inputs)==2


def test_invalid_arguments_recover(monkeypatch, knowledge):
    model=FakeModel([call('read_procedure',{'bad':'x'}), AIMessage(content='Necesito el nombre de un documento.')])
    monkeypatch.setattr(graph,'get_model',lambda:model)
    data=client.post('/ask',json={'question':'Docker no inicia'}).json()
    assert data['trace'][-1]['status']=='error'


def test_tools_do_not_read_external_files_and_redact():
    assert 'error' in tools.read_procedure.invoke({'source':'../../.env'})
    result=tools.analyze_logs.invoke({'log_text':'connection refused password=secret123\nBearer abc123'})
    assert result['matched'] and 'secret123' not in str(result)
    assert '[REDACTADO]' in result['findings'][0]['evidence']
    assert not tools.analyze_logs.invoke({'log_text':'todo funciona'})['matched']


class FakeEmbeddings(Embeddings):
    document_calls=0
    def embed_documents(self,texts):
        self.document_calls+=1
        return [[float(len(text)),1.0,0.0] for text in texts]
    def embed_query(self,text):
        return [float(len(text)),1.0,0.0]


def test_persistent_index_reused_and_documents_changed(monkeypatch,tmp_path):
    kb=tmp_path/'kb';kb.mkdir();document=kb/'docker.md'
    document.write_text('Comprueba el estado de WSL.',encoding='utf-8')
    embeddings=FakeEmbeddings();settings=Settings(_env_file=None,chroma_dir=tmp_path/'index')
    monkeypatch.setattr(rag,'KB_DIR',kb)
    monkeypatch.setattr(rag,'get_settings',lambda:settings)
    monkeypatch.setattr(rag,'OllamaEmbeddings',lambda **_:embeddings)
    assert rag.build_retriever().invoke('WSL')[0].metadata['source']=='docker.md'
    assert embeddings.document_calls==1
    rag.build_retriever().invoke('Docker');assert embeddings.document_calls==1
    document.write_text('Recopila logs antes de escalar.',encoding='utf-8')
    assert 'logs' in rag.build_retriever().invoke('logs')[0].page_content
    assert embeddings.document_calls==2
    settings.ollama_embedding_model='otro-modelo';rag.build_retriever()
    assert embeddings.document_calls==3


def test_ready_and_missing_models(monkeypatch):
    def tags(*args,**kwargs):
        return httpx.Response(200, json={'models':[{'name':'llama3.2:3b'},{'name':'nomic-embed-text:latest'}]}, request=httpx.Request('GET','http://localhost'))
    monkeypatch.setattr(main.httpx,'get',tags)
    assert main.ready()['ready']
    monkeypatch.setattr(main.httpx,'get',lambda *a,**k:httpx.Response(200,json={'models':[]},request=httpx.Request('GET','http://localhost')))
    assert len(main.ready()['missing_models'])==2


def test_session_capacity_concurrency_and_expiry(monkeypatch):
    from app import sessions as module
    settings=Settings(_env_file=None,max_sessions=1,session_ttl_seconds=60)
    monkeypatch.setattr(module,'get_settings',lambda:settings)
    store=SessionStore()
    from fastapi import HTTPException
    with store.conversation(None) as (sid,session):
        with pytest.raises(HTTPException) as busy:
            with store.conversation(sid):pass
        assert busy.value.status_code==409
        with pytest.raises(HTTPException) as full:
            with store.conversation(None):pass
        assert full.value.status_code==503
        store.append(session,'Pregunta','', 'Respuesta')
    session.updated-=61
    with pytest.raises(HTTPException) as expired:
        with store.conversation(sid):pass
    assert expired.value.status_code==404


def test_actual_ollama_adapters_with_simulated_http(monkeypatch, tmp_path):
    """Ejercita SDK, embeddings, Chroma, llamadas a herramientas y API sin modelo real."""
    import json
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    requests = []
    def handle(request):
        data = json.loads(request.content)
        requests.append((request.url.path, data))
        if request.url.path == '/api/embed':
            inputs = data['input']
            if isinstance(inputs, str):
                inputs = [inputs]
            return httpx.Response(200, json={'model': data['model'], 'embeddings': [[float(len(t)), 1.0, 0.0] for t in inputs]})
        assert request.url.path == '/api/chat'
        if data['messages'][-1]['role'] == 'tool':
            message = {'role': 'assistant', 'content': 'Según docker.md, comprueba WSL y recopila el error.'}
        else:
            assert len(data['tools']) == 4
            message = {'role': 'assistant', 'content': '', 'tool_calls': [
                {'function': {'name': 'analyze_logs', 'arguments': {'log_text': 'OOMKilled=true'}}}]}
        result = {'model': data['model'], 'message': message, 'done': True,
                  'done_reason': 'stop', 'prompt_eval_count': 10, 'eval_count': 10}
        return httpx.Response(200, content=(json.dumps(result) + '\n').encode(), headers={'Content-Type': 'application/x-ndjson'})
    transport = httpx.MockTransport(handle)
    kb = tmp_path / 'kb'; kb.mkdir()
    (kb / 'docker.md').write_text('Comprueba el estado de WSL.', encoding='utf-8')
    monkeypatch.setattr(rag, 'KB_DIR', kb)
    monkeypatch.setattr(rag, 'get_settings', lambda: Settings(_env_file=None, chroma_dir=tmp_path / 'index'))
    monkeypatch.setattr(rag, 'OllamaEmbeddings', lambda **kw: OllamaEmbeddings(**{**kw, 'client_kwargs': {'transport': transport, 'trust_env': False}}))
    monkeypatch.setattr(graph, 'get_model', lambda: ChatOllama(model='llama3.2:3b', client_kwargs={'transport': transport, 'trust_env': False}))
    response = client.post('/ask', json={'question': 'Docker no inicia', 'logs': 'OOMKilled=true'})
    assert response.status_code == 200
    assert response.json()['trace'][-1]['tool'] == 'analyze_logs'
    assert response.json()['sources'][0]['source'] == 'docker.md'
    assert sum(path == '/api/chat' for path, _ in requests) == 2


def test_tool_call_budget(monkeypatch, knowledge):
    settings = Settings(_env_file=None, max_tool_calls=1)
    monkeypatch.setattr(graph, 'get_settings', lambda: settings)
    calls = [{'name': 'analyze_logs', 'args': {'log_text': 'timeout'}, 'id': str(i), 'type': 'tool_call'} for i in range(3)]
    model = FakeModel([AIMessage(content='', tool_calls=calls), AIMessage(content='Resumen limitado.')])
    monkeypatch.setattr(graph, 'get_model', lambda: model)
    data = client.post('/ask', json={'question': 'Docker no inicia'}).json()
    assert data['limit_reached']
    assert [t['status'] for t in data['trace'][1:]] == ['ok', 'skipped', 'skipped']


def test_openapi_contains_extended_schema():
    schema = client.get('/openapi.json').json()
    assert '/ready' in schema['paths']
    assert '/sessions/{session_id}' in schema['paths']
    assert 'trace' in schema['components']['schemas']['AskResponse']['properties']
