import logging
from datetime import datetime
from pathlib import Path

class AgentLogger:
    def __init__(self, log_dir="logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger("agent_logger")
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        file_handler = logging.FileHandler(self.log_dir / f"agents_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

    def log_workflow_step(self, agent_name, message):
        self.logger.info(f"{agent_name}: {message}")

    def log_agent_output(self, agent_name, output, method, duration):
        self.logger.debug(f"{agent_name} {method} output: {output} ({duration}s)")

    def log_inter_agent_pass(self, from_agent, to_agent, data_size):
        self.logger.info(f"🔗 PASS: {from_agent} → {to_agent} | Size: {data_size}")

agent_logger = AgentLogger()