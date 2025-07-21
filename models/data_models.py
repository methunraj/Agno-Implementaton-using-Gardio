from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class FileInfo(BaseModel):
    """Information about the file being processed."""
    name: str = Field(description="File name")
    type: str = Field(description="File type/extension")
    size_mb: float = Field(description="File size in MB")
    path: str = Field(description="Full file path")


class SimplifiedAgentConfig(BaseModel):
    """Simplified configuration for agent creation without complex nesting."""
    instructions: str = Field(description="Single string instructions")
    requirement_type: str = Field(default="standard", description="Type of requirements")
    custom_notes: List[str] = Field(default_factory=list, description="Simple notes")


class ProcessingPlan(BaseModel):
    """Simplified processing plan for document analysis."""
    # Basic plan information
    document_type: str = Field(description="Document type (financial, legal, technical, etc.)")
    analysis_objective: str = Field(description="Primary analysis objective")
    complexity: str = Field(default="moderate", description="Complexity level")
    processing_strategy: str = Field(description="Overall processing strategy")
    
    # Essential configurations (simplified)
    agent_configs: Dict[str, str] = Field(
        default_factory=dict, 
        description="Simple agent configuration summaries"
    )
    
    # Simple schema suggestions using basic types
    data_fields: List[str] = Field(description="List of suggested data fields to extract")
    validation_rules: List[str] = Field(default_factory=list, description="Validation rules")
    output_formats: List[str] = Field(default_factory=list, description="Required output formats")
    
    # Simple notes and requirements
    requirements: List[str] = Field(default_factory=list, description="Processing requirements")
    notes: str = Field(default="", description="Additional notes")


class AgentConfiguration(BaseModel):
    """Configuration for a dynamically created agent."""
    instructions: List[str] = Field(description="Specific instructions for this agent")
    custom_prompt_template: Optional[str] = Field(default="", description="Custom prompt template for this agent")
    special_requirements: List[str] = Field(default_factory=list, description="Special requirements or constraints")


class DataPoint(BaseModel):
    """Individual data point extracted from document."""
    field_name: str = Field(description="Name of the data field")
    value: str = Field(description="Value of the field")
    data_type: Optional[str] = Field(default="", description="Type of data (text, number, date, etc.)")
    category: Optional[str] = Field(default="", description="Category or section this data belongs to")
    unit: Optional[str] = Field(default="", description="Unit of measurement if applicable")
    period: Optional[str] = Field(default="", description="Time period if applicable")
    confidence_score: float = Field(description="Confidence score for the extraction (0-1)")
    source_location: Optional[str] = Field(default="", description="Location in document where data was found")


class ExtractedData(BaseModel):
    """Structured data extracted from the document."""
    data_points: List[DataPoint] = Field(description="List of extracted data points")
    extraction_notes: str = Field(default="", description="Notes about the extraction process")
    confidence_score: float = Field(description="Overall confidence score for the extraction")
    extraction_timestamp: datetime = Field(default_factory=datetime.now, description="When extraction was performed")
    document_summary: Optional[str] = Field(default="", description="Brief summary of the document content")


class DataInsight(BaseModel):
    """Individual insight from data analysis."""
    insight_type: str = Field(description="Type of insight (trend, comparison, etc.)")
    description: str = Field(description="Description of the insight")
    supporting_data: List[str] = Field(description="Data points that support this insight")
    importance_level: str = Field(description="Importance level (high, medium, low)")


class DataCategory(BaseModel):
    """A category of organized data."""
    category_name: str = Field(description="Name of the data category")
    data_points: Dict[str, str] = Field(description="Key-value pairs of data in this category")
    
class ArrangedData(BaseModel):
    """Organized and analyzed data."""
    organized_categories: List[DataCategory] = Field(
        description="Data organized into logical categories"
    )
    insights: List[DataInsight] = Field(description="Insights generated from the data")
    summary: str = Field(description="Summary of the arranged data")
    arrangement_notes: str = Field(description="Notes about the arrangement process")


class CodeGenerationResult(BaseModel):
    """Result of code generation and execution."""
    generated_code: str = Field(description="The generated Python code")
    execution_result: str = Field(description="Result of code execution")
    output_files: List[str] = Field(description="List of output files created")
    execution_success: bool = Field(description="Whether code execution was successful")
    error_messages: List[str] = Field(default_factory=list, description="Any error messages encountered")


class DocumentAnalysisResult(BaseModel):
    """Complete result of document analysis team workflow."""
    document_type: str = Field(description="Type of document analyzed")
    analysis_objective: str = Field(description="Original analysis objective")
    processing_summary: str = Field(description="Summary of the entire processing workflow")
    
    # Results from each stage
    planning_notes: str = Field(description="Notes from the planning stage")
    prompts_created: str = Field(description="Summary of prompts and schemas created")
    data_extracted: str = Field(description="Summary of data extraction results")
    data_arranged: str = Field(description="Summary of data arrangement and insights")
    code_generated: str = Field(description="Summary of code generation and execution")
    
    # Final outputs
    key_findings: List[str] = Field(description="Key findings from the analysis")
    output_files_created: List[str] = Field(description="List of output files created")
    success: bool = Field(description="Whether the analysis completed successfully")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations based on analysis")


class ExtractionField(BaseModel):
    """Individual field specification for data extraction."""
    field_name: str = Field(description="Name of the field to extract")
    field_type: str = Field(description="Type of data (text, number, date, etc.)")
    description: str = Field(description="Description of what this field represents")
    required: bool = Field(default=True, description="Whether this field is required")

class AgentPrompt(BaseModel):
    """Prompt configuration for a specific agent."""
    agent_name: str = Field(description="Name of the agent")
    specialized_instructions: List[str] = Field(description="Specialized instructions for this agent")
    input_requirements: List[str] = Field(description="What input this agent needs")
    output_requirements: List[str] = Field(description="What output this agent should produce")
    success_criteria: List[str] = Field(description="Criteria for successful completion")

class PromptsAndSchemas(BaseModel):
    """Prompts and schemas for all agents in the workflow."""
    # Data extraction specific
    extraction_prompt: str = Field(description="Optimized prompt for data extraction")
    extraction_fields: List[ExtractionField] = Field(
        description="List of fields to extract from the document"
    )
    arrangement_rules: List[str] = Field(description="Rules for organizing extracted data")
    validation_criteria: List[str] = Field(description="Criteria for validating extracted data")
    
    # All agent prompts
    agent_prompts: List[AgentPrompt] = Field(description="Specialized prompts for each agent")
    workflow_coordination: List[str] = Field(description="Instructions for coordinating between agents")
    quality_assurance: List[str] = Field(description="Quality assurance guidelines for all agents")