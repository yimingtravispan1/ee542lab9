"""Authenticated document APIs; every document and conversation is owner-scoped."""
from functools import lru_cache

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from document_processing import MAX_FILE_BYTES
from rag_service import RagError, RagService, service_error


@lru_cache
def get_rag_service():
    return RagService()


async def api_call(operation):
    try:
        return await operation
    except RagError as error:
        raise HTTPException(error.status_code, str(error)) from error
    except Exception as error:
        raise HTTPException(503, service_error(error)) from error


class RagQuestion(BaseModel):
    conversation_id: str = Field(min_length=36, max_length=36)
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(default_factory=list, max_length=100)


def create_rag_router(current_user):
    router = APIRouter(prefix='/api', tags=['Documents'])

    @router.get('/rag/status')
    async def status(user=Depends(current_user), service=Depends(get_rag_service)):
        try:
            await service.qdrant.get_collections()
            vector_ready = True
        except Exception:
            vector_ready = False
        return {'openai_configured': service.configured, 'qdrant_ready': vector_ready, 'embedding_model': service.embedding_model, 'chat_model': service.chat_model_name, 'chunk_size': 500, 'chunk_overlap': 100}

    @router.post('/documents', status_code=201)
    async def upload(files: list[UploadFile] = File(...), user=Depends(current_user), service=Depends(get_rag_service)):
        if not 1 <= len(files) <= 10:
            raise HTTPException(422, 'Upload between 1 and 10 files at a time.')
        documents, errors = [], []
        for file in files:
            try:
                data = await file.read(MAX_FILE_BYTES + 1)
                documents.append(await api_call(service.ingest(user.id, file.filename or 'document', data)))
            except HTTPException as error:
                errors.append({'filename': file.filename, 'error': error.detail})
            finally:
                await file.close()
        return {'documents': documents, 'errors': errors}

    @router.get('/documents')
    async def documents(user=Depends(current_user), service=Depends(get_rag_service)):
        return {'documents': await api_call(service.list_documents(user.id))}

    @router.get('/documents/{doc_id}/chunks')
    async def preview(doc_id: str, user=Depends(current_user), service=Depends(get_rag_service)):
        return {'chunks': await api_call(service.preview(user.id, doc_id))}

    @router.post('/documents/{doc_id}/index', status_code=202)
    async def index(doc_id: str, user=Depends(current_user), service=Depends(get_rag_service)):
        return await api_call(service.start_indexing(user.id, doc_id))

    @router.delete('/documents/{doc_id}')
    async def remove(doc_id: str, user=Depends(current_user), service=Depends(get_rag_service)):
        await api_call(service.delete_document(user.id, doc_id))
        return {'deleted': True}

    @router.post('/rag/conversations', status_code=201)
    async def new_conversation(user=Depends(current_user), service=Depends(get_rag_service)):
        return {'id': await api_call(service.create_conversation(user.id))}

    @router.get('/rag/conversations/{conversation_id}')
    async def conversation(conversation_id: str, user=Depends(current_user), service=Depends(get_rag_service)):
        turns = await api_call(service.conversation_history(user.id, conversation_id))
        return {'turns': [{'question': turn.question, 'answer': turn.answer, 'sources': turn.sources} for turn in turns]}

    @router.post('/rag/ask')
    async def ask(data: RagQuestion, user=Depends(current_user), service=Depends(get_rag_service)):
        question = data.question.strip()
        if not question:
            raise HTTPException(422, 'Question cannot be blank.')
        return await api_call(service.ask(user.id, data.conversation_id, question, data.document_ids))

    return router
