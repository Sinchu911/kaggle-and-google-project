import logging
import sys
from dotenv import load_dotenv
from app.agent import Orchestrator

def main():
    # 1. Load environment variables
    load_dotenv()

    # 2. Configure logging to print live info to console in real-time
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout
    )

    # 3. Initialize the Orchestrator
    orchestrator = Orchestrator()

    # 4. Prompt user for custom receipt/bill text
    print("\n" + "="*50)
    print("Welcome to the Global Compliance Auditor AI Agent")
    print("="*50 + "\n")
    
    raw_text = input("Paste your raw receipt/bill text here: ")
    if not raw_text.strip():
        print("Error: Input text cannot be empty.")
        return

    print("\nProcessing your request through the multi-agent compliance pipeline...\n")

    # 5. Pass input into the pipeline
    result = orchestrator.audit_expense(raw_text)

    # 6. Output the final report
    if result and "report" in result:
        print("\n" + "="*50)
        print("FINAL COMPLIANCE AUDIT REPORT SUMMARY")
        print("="*50 + "\n")
        print(result["report"])
        print("\n" + "="*50 + "\n")
    else:
        print("\nPipeline error: Failed to generate compliance report.")

if __name__ == "__main__":
    main()
