# Pydantic response models matching the Neo4j schema.
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict = {}


class GraphLink(BaseModel):
    source: str
    target: str
    relationship: str
    properties: dict = {}


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


class CourseOut(BaseModel):
    code: str
    name: str


class CourseVersionOut(BaseModel):
    id: str
    course_code: str
    course_name: str
    year: int
    course_url: Optional[str] = None
    course_details: Optional[str] = None
    course_learning_outcomes: list = []


class RequisiteRelOut(BaseModel):
    subject_version_id: str
    code: str
    name: str
    year: int
    item_id: str
    item_type: Optional[str] = None
    rule: str


class AdmissionReqOut(BaseModel):
    detail: str
    item_id: str
    item_type: str
    rule: str


class OtherReqOut(BaseModel):
    note: str
    rule: str


class SubjectRequisitesOut(BaseModel):
    subject_version_id: str
    code: str
    name: str
    year: int
    requisite_rule: Optional[str] = None
    anti_requisite_rule: Optional[str] = None
    prerequisites: list[RequisiteRelOut] = []
    anti_requisites: list[RequisiteRelOut] = []
    admission_requisites: list[AdmissionReqOut] = []
    other_requisites: list[OtherReqOut] = []


class SubjectVersionOut(BaseModel):
    id: str
    code: str
    name: str
    year: int
    url: Optional[str] = None
    credit_points: Optional[str] = None
    type: Optional[str] = None
    faculty: Optional[str] = None
    study_level: Optional[str] = None
    result_type: Optional[str] = None
    total_workload_hours: Optional[str] = None
    description: Optional[str] = None
    learning_outcomes: list = []
    teaching_and_learning_activities: Optional[str] = None
    requisite_rule: Optional[str] = None
    anti_requisite_rule: Optional[str] = None


class SubjectDetailOut(BaseModel):
    code: str
    name: str
    versions: list[SubjectVersionOut] = []


class AreaOfStudyVersionOut(BaseModel):
    id: str
    code: str
    name: str
    year: int
    url: Optional[str] = None
    credit_points: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None


class AreaOfStudyDetailOut(BaseModel):
    code: str
    name: str
    versions: list[AreaOfStudyVersionOut] = []
