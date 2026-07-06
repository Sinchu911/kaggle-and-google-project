import os
import re
import logging
from pathlib import Path

# Setup logging
logger = logging.getLogger("PolicyEngine")

class PolicyEngine:
    def __init__(self, data_dir: str = "data"):
        """
        Initializes the PolicyEngine pointing to the directory containing regional policy markdown files.
        """
        self.data_dir = Path(__file__).resolve().parent.parent / data_dir

    def lookup_policy(self, country_name: str) -> dict | None:
        """
        Accepts a country name, searches the regional policy markdown files under the
        data directory, parses the rules, and returns a structured dictionary.
        
        Returns:
            dict: {
                "country": str,
                "currency": str,
                "vat_rate": float,
                "dinner_limit": float,
                "lodging_limit": float,
                "region": str
            }
            or None if the country is not found.
        """
        if not country_name:
            logger.warning("Empty country name provided to lookup_policy.")
            return None

        country_clean = country_name.strip().lower()
        
        # Handle country aliases/variations
        if country_clean in ("us", "usa", "united states of america"):
            country_clean = "united states"

        if not self.data_dir.exists():
            logger.error(f"Data directory '{self.data_dir}' does not exist.")
            return None

        # Scan all markdown files in data_dir
        for file_path in self.data_dir.glob("*.md"):
            # Region is prefix of file name, e.g. "US" from "US_policy.md"
            region = file_path.stem.split("_")[0]
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Failed to read policy file '{file_path}': {e}")
                continue

            # Split content by H2 headers (starting with '## ')
            sections = re.split(r'^##\s+', content, flags=re.MULTILINE)
            
            for section in sections[1:]:  # skip the preamble/file title
                lines = section.split('\n')
                if not lines:
                    continue
                
                section_country = lines[0].strip().lower()
                
                # Check if this is the country we're looking for
                if section_country == country_clean:
                    policy = {
                        "country": lines[0].strip(),
                        "currency": None,
                        "vat_rate": 0.0,
                        "dinner_limit": 0.0,
                        "lodging_limit": 0.0,
                        "region": region
                    }
                    
                    # Parse bullet points under the country header
                    for line in lines[1:]:
                        line_stripped = line.strip()
                        
                        # Stop if we hit another header level
                        if line_stripped.startswith("#"):
                            break
                        
                        # Match bullet points: - Key: Value
                        match = re.match(r'^[-*]\s*([^:]+):\s*(.+)$', line_stripped)
                        if match:
                            key = match.group(1).strip().lower()
                            val = match.group(2).strip()
                            
                            def extract_number(s: str) -> float:
                                # Regex to find integers or floats
                                num_match = re.search(r'[\d,]+(?:\.\d+)?', s)
                                if num_match:
                                    return float(num_match.group(0).replace(',', ''))
                                return 0.0

                            if "dinner" in key:
                                policy["dinner_limit"] = extract_number(val)
                            elif "lodging" in key:
                                policy["lodging_limit"] = extract_number(val)
                            elif "vat" in key:
                                pct = extract_number(val)
                                policy["vat_rate"] = pct / 100.0 if pct > 0 else 0.0
                            elif "currency" in key:
                                policy["currency"] = val
                    
                    logger.info(f"Successfully retrieved policy for country '{country_name}': {policy}")
                    return policy

        logger.warning(f"No policy found for country '{country_name}'.")
        return None
