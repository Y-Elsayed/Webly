from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from webly.service.dependencies import get_chat_service
from webly.service.schemas import (
    ChatListResponse,
    ChatResponse,
    ChatUpdateRequest,
    ErrorResponse,
)
from webly.service.services.chat_service import ChatService

router = APIRouter(prefix="/v1/projects", tags=["chats"])


def _chat_response(payload: dict) -> ChatResponse:
    return ChatResponse.model_validate(payload)


@router.get(
    "/{project}/chats",
    response_model=ChatListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_project_chats(
    project: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatListResponse:
    try:
        return ChatListResponse(items=chat_service.list_chats(project))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{project}/chats/{chat}",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_project_chat(
    project: str,
    chat: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        payload = chat_service.get_chat(project, chat)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _chat_response(payload)


@router.put(
    "/{project}/chats/{chat}",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}},
)
def save_project_chat(
    project: str,
    chat: str,
    request: ChatUpdateRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        payload = chat_service.save_chat(project, chat, request.model_dump(exclude_none=True))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _chat_response(payload)


@router.delete(
    "/{project}/chats/{chat}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={404: {"model": ErrorResponse}},
)
def delete_project_chat(
    project: str,
    chat: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> Response:
    try:
        chat_service.delete_chat(project, chat)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
