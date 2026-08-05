#!/usr/bin/env python3
"""
Demo Setup Script - Creates sample data for testing the web dashboard
"""

import json
import os
from datetime import datetime

def create_demo_groups():
    """Create sample groups data for demo purposes"""
    demo_groups = [
        {
            "name": "Python Developers Community",
            "url": "https://www.facebook.com/groups/pythondevelopers"
        },
        {
            "name": "Web Development Enthusiasts",
            "url": "https://www.facebook.com/groups/webdevlovers"
        },
        {
            "name": "AI & Machine Learning",
            "url": "https://www.facebook.com/groups/aimachinelearning"
        },
        {
            "name": "JavaScript Experts",
            "url": "https://www.facebook.com/groups/javascriptexperts"
        },
        {
            "name": "React.js Developers",
            "url": "https://www.facebook.com/groups/reactjsdevelopers"
        },
        {
            "name": "Digital Marketing Masters",
            "url": "https://www.facebook.com/groups/digitalmarketingmasters"
        },
        {
            "name": "Data Science Hub",
            "url": "https://www.facebook.com/groups/datasciencehub"
        },
        {
            "name": "Freelancers United",
            "url": "https://www.facebook.com/groups/freelancersunited"
        },
        {
            "name": "Startup Founders Network",
            "url": "https://www.facebook.com/groups/startupfounders"
        },
        {
            "name": "Tech Entrepreneurs",
            "url": "https://www.facebook.com/groups/techentrepreneurs"
        }
    ]
    
    # Save to the expected file
    with open('autofetched_groups.json', 'w') as f:
        json.dump(demo_groups, f, indent=2)
    
    print(f"✅ Created demo data with {len(demo_groups)} sample groups")
    print("🔗 Sample groups include Python, Web Dev, AI, JavaScript, React, etc.")
    
    return demo_groups

def display_dashboard_info():
    """Display information about the dashboard"""
    print("\n" + "="*60)
    print("🌟 FACEBOOK GROUP FETCHER - WEB DASHBOARD")
    print("="*60)
    print()
    print("📊 FEATURES IMPLEMENTED:")
    print("   ✅ Real-time Progress Tracking (WebSocket)")
    print("   ✅ Interactive Group Visualization") 
    print("   ✅ Advanced Job Scheduling")
    print("   ✅ Multi-format Export (JSON, CSV, Excel, ZIP)")
    print("   ✅ Modern Responsive UI")
    print("   ✅ Search & Filtering")
    print("   ✅ Pagination")
    print("   ✅ Dark Theme")
    print()
    print("🚀 ACCESS DASHBOARD:")
    print("   URL: http://localhost:8080")
    print("   Status: Dashboard running in background")
    print()
    print("📱 PAGES AVAILABLE:")
    print("   • Dashboard (/) - Main control panel")
    print("   • Groups (/groups) - View & manage groups")
    print("   • Scheduler (/scheduler) - Automated jobs")
    print()
    print("⚡ QUICK ACTIONS:")
    print("   • Test with demo data (already loaded)")
    print("   • Try real-time fetching simulation")
    print("   • Export groups in different formats")
    print("   • Schedule automated jobs")
    print()
    print("🎨 UI HIGHLIGHTS:")
    print("   • Beautiful gradient sidebar")
    print("   • Interactive progress bars")
    print("   • Real-time WebSocket updates")
    print("   • Responsive card layouts")
    print("   • Modern Bootstrap 5 design")
    print()
    print("="*60)

if __name__ == '__main__':
    print("🎯 Setting up demo environment...")
    
    # Create demo groups
    groups = create_demo_groups()
    
    # Display dashboard info
    display_dashboard_info()
    
    print("\n💡 NEXT STEPS:")
    print("1. Open http://localhost:8080 in your browser")
    print("2. Explore the dashboard interface")
    print("3. Test group visualization on /groups page")
    print("4. Try the export functionality")
    print("5. Check out the scheduler page")
    print("\n✨ Enjoy the premium web interface!") 