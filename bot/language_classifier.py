"""
Language classifier for Facebook groups
Automatically categorizes groups based on language keywords in their names
"""

import re
import logging

logger = logging.getLogger(__name__)

class LanguageClassifier:
    """Classify groups by language based on keywords in group names"""
    
    # Language patterns (keywords that indicate specific languages)
    LANGUAGE_PATTERNS = {
        'ukrainian': {
            'keywords': [
                'робота', 'роботи', 'вакансії', 'вакансия', 'україна', 'украина', 'українці', 'украинцы',
                'київ', 'киев', 'харків', 'харьков', 'одеса', 'одесса', 'львів', 'львов',
                'дніпро', 'днепр', 'запоріжжя', 'запорожье', 'тернопіль', 'тернополь',
                'україньский', 'український', 'украинский', 'udt', 'українська', 'украинская',
                'прац', 'працевлаштування', 'трудоустройство', 'заробіток', 'заработок'
            ],
            'flag': '🇺🇦'
        },
        'russian': {
            'keywords': [
                'работа', 'работы', 'вакансии', 'вакансия', 'россия', 'российская', 'российский',
                'москва', 'петербург', 'спб', 'друзья', 'друзей', 'русские', 'русский',
                'российские', 'мск', 'русская', 'русским', 'русскую', 'российскую',
                'трудоустройство', 'зарплата', 'подработка', 'фриланс'
            ],
            'flag': '🇷🇺'
        },
        'german': {
            'keywords': [
                'arbeit', 'arbeiten', 'job', 'jobs', 'wohnung', 'wohnungen', 'schweiz', 'deutschland',
                'österreich', 'verkaufen', 'kaufen', 'verkauf', 'auto', 'deutsch', 'deutsche',
                'deutschen', 'zürich', 'berlin', 'münchen', 'wien', 'basel', 'bern',
                'flohmarkt', 'kleinanzeigen', 'immobilien', 'gebrauchtwagen', 'inserate'
            ],
            'flag': '🇩🇪'
        },
        'polish': {
            'keywords': [
                'praca', 'pracy', 'warszawa', 'kraków', 'gdańsk', 'wrocław', 'poznań',
                'łódź', 'katowice', 'bydgoszcz', 'toruń', 'polska', 'polskie', 'polski',
                'polską', 'ogłoszenia', 'mieszkania', 'zatrudnienie', 'pracowników'
            ],
            'flag': '🇵🇱'
        }
    }
    
    @classmethod
    def classify_group(cls, group_name):
        """
        Classify a group's language based on its name
        
        Args:
            group_name (str): Name of the Facebook group
            
        Returns:
            str: Language code ('ukrainian', 'russian', 'german', 'polish', 'unknown')
        """
        if not group_name:
            return 'unknown'
        
        # Convert to lowercase for matching
        name_lower = group_name.lower()
        
        # Score each language based on keyword matches
        language_scores = {}
        
        for language, config in cls.LANGUAGE_PATTERNS.items():
            score = 0
            keywords = config['keywords']
            
            for keyword in keywords:
                # Count occurrences of each keyword (case-insensitive)
                if keyword.lower() in name_lower:
                    # Longer keywords get higher scores
                    score += len(keyword)
                    
                    # Exact word matches get bonus points
                    if re.search(r'\b' + re.escape(keyword.lower()) + r'\b', name_lower):
                        score += 5
            
            if score > 0:
                language_scores[language] = score
        
        # Return the language with the highest score
        if language_scores:
            best_language = max(language_scores, key=language_scores.get)
            logger.debug(f"Group '{group_name}' classified as '{best_language}' (score: {language_scores[best_language]})")
            return best_language
        
        # No language detected
        logger.debug(f"Group '{group_name}' classified as 'unknown'")
        return 'unknown'
    
    @classmethod
    def get_language_info(cls, language_code):
        """Get display information for a language"""
        if language_code in cls.LANGUAGE_PATTERNS:
            return {
                'code': language_code,
                'name': language_code.title(),
                'flag': cls.LANGUAGE_PATTERNS[language_code]['flag']
            }
        return {
            'code': 'unknown',
            'name': 'Unknown',
            'flag': '❓'
        }
    
    @classmethod
    def get_all_languages(cls):
        """Get list of all supported languages"""
        languages = []
        for code, config in cls.LANGUAGE_PATTERNS.items():
            languages.append({
                'code': code,
                'name': code.title(),
                'flag': config['flag']
            })
        return languages
    
    @classmethod
    def classify_groups_batch(cls, groups):
        """
        Classify multiple groups at once and add language_tag to each group
        
        Args:
            groups (list): List of group dictionaries with 'name' key
            
        Returns:
            list: Groups with added 'language_tag' field
        """
        classified_groups = []
        
        language_stats = {}
        
        for group in groups:
            # Create a copy to avoid modifying original
            classified_group = group.copy()
            
            # Classify the language
            language = cls.classify_group(group.get('name', ''))
            classified_group['language_tag'] = language
            
            # Track statistics
            language_stats[language] = language_stats.get(language, 0) + 1
            
            classified_groups.append(classified_group)
        
        # Log statistics
        logger.info("Language classification completed:")
        for language, count in sorted(language_stats.items()):
            flag = cls.get_language_info(language)['flag']
            logger.info(f"  {flag} {language.title()}: {count} groups")
        
        return classified_groups 