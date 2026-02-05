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
    node_id: str
    node_name: str
    node_content: str
    question: str
    history: List[dict] = []
    selection: str = ""
    user_persona: str = ""

class QuizQuestion(BaseModel):
    id: int
    question: str
    options: List[str]
    correct_index: int
    explanation: str

class GenerateQuizRequest(BaseModel):
    node_id: str
    node_content: str
    difficulty: str = "medium" # easy, medium, hard

class LocateNodeRequest(BaseModel):
    keyword: str
