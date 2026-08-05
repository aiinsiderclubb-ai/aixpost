#!/usr/bin/env python3
"""
Test script for the Message Templates System
"""

import sys
import os

# Add the bot directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

def test_template_manager():
    """Test the MessageTemplateManager directly"""
    print("🧪 Testing MessageTemplateManager...")
    
    try:
        from bot.message_templates import MessageTemplateManager
        
        # Create a test manager
        manager = MessageTemplateManager('test_templates.json')
        
        # Test template generation
        print("\n📝 Testing template generation:")
        for i in range(3):
            message, template_idx, variables = manager.generate_message()
            print(f"  {i+1}. Template #{template_idx + 1}: {message}")
            print(f"     Variables: {variables}")
        
        # Test statistics
        print("\n📊 Template Statistics:")
        stats = manager.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        print("\n✅ MessageTemplateManager tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing MessageTemplateManager: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run template tests"""
    print("🚀 Starting Template System Tests")
    print("=" * 50)
    
    # Test Template Manager
    success = test_template_manager()
    
    print("\n" + "=" * 50)
    print("📋 TEST SUMMARY:")
    print(f"  Template Manager: {'✅ PASS' if success else '❌ FAIL'}")
    
    if success:
        print("\n🎉 Template system is working!")
        return 0
    else:
        print("\n⚠️ Tests failed.")
        return 1

if __name__ == "__main__":
    exit(main()) 