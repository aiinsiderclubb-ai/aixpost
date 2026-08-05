"""
Post Performance Analyzer
Collects metrics from Facebook posts for analytics
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re

logger = logging.getLogger(__name__)

class PostAnalyzer:
    """Analyzes Facebook post performance and collects metrics"""
    
    def __init__(self, driver=None):
        self.driver = driver
    
    def _extract_number_from_text(self, text: str) -> int:
        """Extract number from text with K, M suffixes"""
        if not text:
            return 0
            
        try:
            # Remove extra whitespace and convert to lowercase
            text = text.strip().lower()
            
            # Look for numbers with K, M, B suffixes
            number_patterns = [
                r'(\d+(?:\.\d+)?)\s*k',  # 1.2K, 15K
                r'(\d+(?:\.\d+)?)\s*m',  # 1.5M, 2M
                r'(\d+(?:\.\d+)?)\s*b',  # 1.2B
                r'(\d+(?:,\d+)*)',       # 1,234
                r'(\d+)'                 # 123
            ]
            
            for i, pattern in enumerate(number_patterns):
                match = re.search(pattern, text)
                if match:
                    number = float(match.group(1).replace(',', ''))
                    
                    if i == 0:  # K suffix
                        return int(number * 1000)
                    elif i == 1:  # M suffix
                        return int(number * 1000000)
                    elif i == 2:  # B suffix
                        return int(number * 1000000000)
                    else:  # No suffix
                        return int(number)
            
            return 0
            
        except Exception as e:
            logger.debug(f"Error extracting number from '{text}': {e}")
            return 0
    
    def _calculate_performance_score(self, metrics: Dict) -> float:
        """Calculate overall performance score"""
        try:
            likes = metrics.get('likes', 0)
            comments = metrics.get('comments', 0)
            shares = metrics.get('shares', 0)
            
            # Weight different engagement types
            weighted_score = (
                likes * 1.0 +          # Likes have base weight
                comments * 3.0 +       # Comments are more valuable
                shares * 5.0           # Shares are most valuable
            )
            
            # Normalize to 0-100 scale (logarithmic)
            if weighted_score == 0:
                return 0.0
            
            import math
            score = min(100.0, (math.log10(weighted_score + 1) * 20))
            return round(score, 2)
            
        except Exception as e:
            logger.debug(f"Error calculating performance score: {e}")
            return 0.0