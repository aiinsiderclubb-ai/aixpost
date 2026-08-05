#!/usr/bin/env python3
"""
Test script for language classification functionality
Tests the automatic language detection and classification of Facebook groups
"""

import json
import logging
from bot.language_classifier import LanguageClassifier

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_individual_classification():
    """Test classification of individual group names"""
    print("\n🔍 Testing Individual Group Classification")
    print("=" * 50)
    
    test_groups = [
        # Ukrainian groups
        "+10 Вакансії з УДТ (UDT). Робота для фахівців. Praca z UDT.",
        "Робота в Україні - вакансії Київ",
        "Українці в Польщі - робота і житло",
        
        # Russian groups  
        "Работа в Москве - вакансии",
        "Друзья в России - объявления",
        "Российские вакансии и работа",
        
        # German groups
        "AUTO Kaufen & Verkaufen SCHWEIZ",
        "Wohnung mieten Deutschland",
        "Arbeit und Jobs in Österreich",
        "Flohmarkt Kleinanzeigen",
        
        # Polish groups
        "Praca w Warszawie - ogłoszenia",
        "Bydgoszcz Polska praca zatrudnienie",
        
        # Mixed/Unknown
        "Facebook Group 592890606613080",
        "Du bisch us em Thurgau wenn ..."
    ]
    
    for group_name in test_groups:
        language = LanguageClassifier.classify_group(group_name)
        lang_info = LanguageClassifier.get_language_info(language)
        
        print(f"{lang_info['flag']} {lang_info['name']:10} | {group_name}")

def test_batch_classification():
    """Test batch classification using actual groups data"""
    print("\n📊 Testing Batch Classification")
    print("=" * 50)
    
    # Try to load actual groups data
    try:
        with open('autofetched_groups.json', 'r', encoding='utf-8') as f:
            groups = json.load(f)
        
        # Take a sample for testing
        sample_groups = groups[:20] if len(groups) > 20 else groups
        
        # Classify the sample
        classified_groups = LanguageClassifier.classify_groups_batch(sample_groups)
        
        # Count by language
        language_counts = {}
        for group in classified_groups:
            lang = group.get('language_tag', 'unknown')
            language_counts[lang] = language_counts.get(lang, 0) + 1
        
        print(f"Sample size: {len(classified_groups)} groups")
        print("\nLanguage distribution:")
        for language, count in sorted(language_counts.items()):
            lang_info = LanguageClassifier.get_language_info(language)
            print(f"  {lang_info['flag']} {lang_info['name']:10}: {count:3d} groups")
            
        # Show some examples
        print(f"\nExamples from classification:")
        for language in language_counts.keys():
            examples = [g for g in classified_groups if g.get('language_tag') == language][:2]
            if examples:
                lang_info = LanguageClassifier.get_language_info(language)
                print(f"\n{lang_info['flag']} {lang_info['name']} examples:")
                for example in examples:
                    print(f"  • {example['name'][:80]}...")
                    
    except FileNotFoundError:
        print("❌ autofetched_groups.json not found")
        print("   Run manual_fetch_groups.py first to create test data")
    except Exception as e:
        logger.error(f"Error testing batch classification: {e}")

def test_supported_languages():
    """Test getting all supported languages"""
    print("\n🌍 Supported Languages")
    print("=" * 50)
    
    languages = LanguageClassifier.get_all_languages()
    
    for lang in languages:
        print(f"{lang['flag']} {lang['name']} ({lang['code']})")

def test_classification_accuracy():
    """Test classification accuracy with known examples"""
    print("\n🎯 Testing Classification Accuracy")
    print("=" * 50)
    
    # Test cases with expected results
    test_cases = [
        ("Робота в Україні для всіх", "ukrainian"),
        ("Вакансії Київ - робота", "ukrainian"),
        ("Работа в России друзья", "russian"),
        ("Российские вакансии", "russian"),
        ("Arbeit in der Schweiz", "german"),
        ("Auto verkaufen Deutschland", "german"),
        ("Praca w Polsce Warszawa", "polish"),
        ("Random English Group", "unknown"),
        ("", "unknown"),
    ]
    
    correct = 0
    total = len(test_cases)
    
    for group_name, expected in test_cases:
        actual = LanguageClassifier.classify_group(group_name)
        is_correct = actual == expected
        
        if is_correct:
            correct += 1
            status = "✅"
        else:
            status = "❌"
            
        print(f"{status} '{group_name}' -> Expected: {expected}, Got: {actual}")
    
    accuracy = (correct / total) * 100
    print(f"\n📈 Accuracy: {correct}/{total} = {accuracy:.1f}%")

def main():
    """Run all tests"""
    print("🚀 Language Classification Test Suite")
    print("=" * 60)
    
    try:
        test_individual_classification()
        test_batch_classification()
        test_supported_languages()
        test_classification_accuracy()
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    main() 