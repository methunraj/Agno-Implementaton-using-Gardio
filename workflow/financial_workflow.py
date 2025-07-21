"""
Financial Data Extraction Workflow - Proper Agno Implementation
Uses Agno Workflow 2.0 with built-in streaming and proper agent configuration
"""

from agno.workflow.v2.workflow import Workflow
from agno.workflow.v2.step import Step
from agno.workflow.v2.types import StepInput, StepOutput
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.file import FileTools
from agno.tools.python import PythonTools
from agno.media import File
from pathlib import Path
from agno.utils.log import logger
from typing import Optional, Dict, Any
import json
import logging
import uuid
from config.settings import settings

logger = logging.getLogger(__name__)


class FinancialDataExtractionWorkflow:
    """Simple workflow class that creates proper Agno Workflows 2.0 instance"""
    
    def __init__(self, session_id: str = None):
        # Set session directory
        self.session_id = session_id or f"financial_extraction_{uuid.uuid4().hex[:8]}"
        self.session_output_dir = Path(settings.TEMP_DIR) / self.session_id / "output"
        self.session_output_dir.mkdir(parents=True, exist_ok=True)
        
    def create_workflow(self) -> Workflow:
        """Create and return a proper Agno Workflows 2.0 instance"""
        
        # Create agents
        data_extractor = self.get_data_extractor()
        data_arranger = self.get_data_arranger() 
        coding_agent = self.get_coding_agent()
        
        # Create workflow with steps
        workflow = Workflow(
            name="FinancialDataExtractionWorkflow",
            description="Financial data extraction using Agno Workflows 2.0",
            steps=[
                Step(name="extract_data", agent=data_extractor),
                Step(name="arrange_data", agent=data_arranger),
                Step(name="generate_excel", agent=coding_agent)
            ]
        )
        
        return workflow
    
    def get_data_extractor(self) -> Agent:
        """Data extractor agent with proper configuration"""
        data_path = Path("Prompts/data_extractor.json")
        rules_path = Path("Rules/data_extractor_rules.json")
        
        with open(data_path) as f:
            prompt_config = json.load(f)
        with open(rules_path) as f:
            rules_config = json.load(f)
        
        return Agent(
            name="FinancialDataExtractor",
            model=Gemini(
                id=settings.DATA_EXTRACTOR_MODEL,
                api_key=settings.GOOGLE_AI_API_KEY
            ),
            description="Extracts financial data from documents",
            instructions=[
                prompt_config["system_prompt"],
                prompt_config["main_prompt"],
                *rules_config["agent_rules"]["instructions"],
                *rules_config["agent_rules"]["validation_rules"]
            ],
            debug_mode=True
        )

    def get_data_arranger(self) -> Agent:
        """Data arranger agent with file tools"""
        data_path = Path("Prompts/data_arranger.json")
        rules_path = Path("Rules/data_arranger_rules.json")
        
        with open(data_path) as f:
            prompt_config = json.load(f)
        with open(rules_path) as f:
            rules_config = json.load(f)
            
        return Agent(
            name="FinancialDataArranger",
            model=Gemini(
                id=settings.DATA_ARRANGER_MODEL,
                api_key=settings.GOOGLE_AI_API_KEY
            ),
            description="Organizes extracted financial data",
            tools=[FileTools(base_dir=Path(self.session_output_dir))],
            instructions=[
                prompt_config["system_prompt"],
                prompt_config["main_prompt"],
                *rules_config["agent_rules"]["instructions"],
                *rules_config["agent_rules"]["organization_requirements"]
            ],
            debug_mode=True
        )

    def get_coding_agent(self) -> Agent:
        """Coding agent with Python tools"""
        data_path = Path("Prompts/coding_agent.json")
        rules_path = Path("Rules/coding_agent_rules.json")
        
        with open(data_path) as f:
            prompt_config = json.load(f)
        with open(rules_path) as f:
            rules_config = json.load(f)
            
        return Agent(
            name="FinancialExcelGenerator",
            model=Gemini(
                id=settings.CODE_GENERATOR_MODEL,
                api_key=settings.GOOGLE_AI_API_KEY
            ),
            description="Generates Excel reports from financial data",
            tools=[
                PythonTools(
                    base_dir=Path(self.session_output_dir),
                    pip_install=True,
                    run_code=True,
                    save_and_run=True,
                    safe_globals={},
                    safe_locals={}
                ),
                FileTools(base_dir=Path(self.session_output_dir))
            ],
            instructions=[
                prompt_config["system_prompt"],
                prompt_config["main_prompt"],
                *rules_config["agent_rules"]["instructions"],
                *rules_config["agent_rules"]["execution_requirements"],
                *rules_config["agent_rules"]["output_requirements"],
                *rules_config["agent_rules"]["data_organization_requirements"]
            ],
            debug_mode=True
        )

    async def run_financial_extraction(self, file_path: str, session_id: str = None):
        """Run the complete financial extraction workflow with section-by-section complete output"""
        import uuid
        
        try:
            # Update session if provided
            if session_id:
                self.session_id = session_id
                self.session_output_dir = Path(settings.TEMP_DIR) / session_id / "output"
                self.session_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create agents individually for section-by-section execution
            data_extractor = self.get_data_extractor()
            data_arranger = self.get_data_arranger()
            coding_agent = self.get_coding_agent()
            
            # Step 1: Data Extraction - Complete output
            yield {
                "type": "step_start",
                "step": "data_extraction",
                "message": "Starting financial data extraction..."
            }
            
            extraction_prompt = f"Extract financial data from document: {file_path}. Provide complete structured output."
            extraction_response = await data_extractor.arun(message=extraction_prompt)
            
            yield {
                "type": "step_complete",
                "step": "data_extraction", 
                "data": extraction_response.content,
                "agent": "Data Extractor Agent"
            }
            
            # Step 2: Data Arrangement - Complete output
            yield {
                "type": "step_start",
                "step": "data_arrangement",
                "message": "Organizing and analyzing extracted data..."
            }
            
            arrangement_prompt = f"Organize and analyze this extracted data: {extraction_response.content}. Provide complete structured output with insights."
            arrangement_response = await data_arranger.arun(message=arrangement_prompt)
            
            yield {
                "type": "step_complete",
                "step": "data_arrangement",
                "data": arrangement_response.content,
                "agent": "Data Arranger Agent"
            }
            
            # Step 3: Excel Generation - Complete output
            yield {
                "type": "step_start",
                "step": "excel_generation",
                "message": "Generating comprehensive Excel reports..."
            }
            
            # Hybrid approach: Direct JSON as Priority 1, File as Priority 2
            coding_prompt = f"""
Generate Excel reports using the following hybrid data approach:

PRIORITY 1 (PREFERRED): Use the JSON data provided directly below:
{arrangement_response.content}

PRIORITY 2 (FALLBACK): If the above JSON data cannot be parsed, try reading from file 'arranged_comprehensive_financial_data.json' in current directory.

IMPORTANT INSTRUCTIONS:
- First attempt to parse and use the JSON data provided directly above
- If JSON parsing fails, fall back to reading from the file
- Work with whatever data structure is available (don't require specific 12-worksheet format)
- Create Excel worksheets based on the actual data structure found
- Handle missing or incomplete data gracefully
- Always create at least one worksheet with available data
- Save Excel file with timestamp: Financial_Report_YYYYMMDD_HHMMSS.xlsx

Create comprehensive worksheets and save files successfully.
"""
            coding_response = await coding_agent.arun(message=coding_prompt)
            
            yield {
                "type": "step_complete",
                "step": "excel_generation",
                "data": coding_response.content,
                "agent": "Coding Agent"
            }
            
            # Final result with all outputs
            yield {
                "type": "final_result", 
                "data": {
                    "extraction_result": extraction_response.content,
                    "arrangement_result": arrangement_response.content,
                    "coding_result": coding_response.content
                },
                "session_id": self.session_id,
                "session_dir": str(self.session_output_dir)
            }
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            yield {
                "type": "error",
                "message": f"Workflow failed: {str(e)}"
            }
            raise
