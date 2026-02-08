from typing import List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime
import uuid

class Node(BaseModel):
    node_id: str
    parent_node_id: str
    node_name: str
    node_level: int
    node_content: str = ""
    node_type: Literal["original", "custom", "extend"] = "original"
    create_time: Optional[datetime] = None
    is_read: bool = False
    quiz_score: Optional[int] = None

class Annotation(BaseModel):
    anno_id: str
    node_id: str
    question: str
    answer: str
    anno_summary: str
    source_type: Literal["internal", "external"] = "internal"
    create_time: datetime = datetime.now()

class GenerateCourseRequest(BaseModel):
    keyword: str
    difficulty: Optional[str] = "medium"
    style: Optional[str] = "academic"
    requirements: Optional[str] = ""

class GenerateSubNodesRequest(BaseModel):
    node_id: str
    node_name: str
    node_level: int

class RedefineContentRequest(BaseModel):
    node_id: str
    node_name: str
    original_content: str
    user_requirement: str
    course_context: Optional[str] = ""
    previous_context: Optional[str] = ""

class ExtendContentRequest(BaseModel):
    node_id: str
    node_name: str
    current_content: str
    user_requirement: str

class AskQuestionRequest(BaseModel):
    course_id: Optional[str] = None
    node_id: str
    node_name: str
    node_content: str
    question: str
    history: List[dict] = []
    selection: Optional[str] = ""
    user_persona: Optional[str] = ""

class AddNodeRequest(BaseModel):
    parent_node_id: str = "root"
    node_name: str = "New Node"

class SaveAnnotationRequest(BaseModel):
    anno_id: Optional[str] = None
    node_id: str
    question: str
    answer: str
    anno_summary: str
    source_type: Literal["user", "ai", "user_saved"] = "user"
    quote: Optional[str] = None

class UpdateNodeRequest(BaseModel):
    node_name: Optional[str] = None
    node_content: Optional[str] = None
    is_read: Optional[bool] = None
    quiz_score: Optional[int] = None

class UpdateAnnotationRequest(BaseModel):
    content: str

class GenerateQuizRequest(BaseModel):
    node_content: str
    node_name: Optional[str] = ""
    difficulty: str = "medium"
    style: Optional[str] = "standard"
    user_persona: Optional[str] = ""
    question_count: int = 3

class SummarizeChatRequest(BaseModel):
    history: List[dict]
    course_context: Optional[str] = ""
    user_persona: Optional[str] = ""

class LocateNodeRequest(BaseModel):
    keyword: str
