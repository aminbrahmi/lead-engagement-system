import os
import sys
import json
import re
from dotenv import load_dotenv
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Import required modules
from agents.writer import create_writer_agent
from orchestration.tasks import create_write_task
from crewai import Crew, Process

def load_leads_from_json(json_path=None):
    """Load leads from the leads_raw.json file"""
    
    if json_path is None:
        # Default path
        json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "leads_raw.json"
        )
    
    print(f"📂 Loading leads from: {json_path}")
    
    if not os.path.exists(json_path):
        print(f"❌ File not found: {json_path}")
        return []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            leads = json.load(f)
        
        print(f"✅ Loaded {len(leads)} leads from JSON file")
        return leads
        
    except Exception as e:
        print(f"❌ Error loading JSON: {e}")
        return []

def filter_qualified_leads(leads, segment_filter=None):
    """Filter leads that are qualified (hot/warm)"""
    
    qualified = []
    
    for lead in leads:
        # Check if lead has been qualified
        if lead.get('status') == 'qualified' and lead.get('keep', True):
            segment = lead.get('segment', 'unknown')
            
            # Apply segment filter if specified
            if segment_filter and segment not in segment_filter:
                continue
            
            # Ensure required fields exist
            if lead.get('name') and lead.get('company') and lead.get('role'):
                qualified.append(lead)
            else:
                print(f"⚠️ Skipping lead with missing data: {lead.get('company', 'Unknown')}")
    
    return qualified

def prepare_leads_for_writer(qualified_leads):
    """Prepare leads in the format expected by the writer agent"""
    
    prepared_leads = []
    
    for lead in qualified_leads:
        prepared_lead = {
            "name": lead.get('name'),
            "company": lead.get('company'),
            "role": lead.get('role'),
            "location": lead.get('location', 'Berlin'),
            "source_url": lead.get('source_url', ''),
            "email": lead.get('email'),
            "email_source": lead.get('email_source'),
            "score": lead.get('score', 70),
            "segment": lead.get('segment', 'hot'),
            "reason": lead.get('reason', ''),
            "keep": True,
            "notes": lead.get('notes', '')
        }
        prepared_leads.append(prepared_lead)
    
    return prepared_leads

def test_writer_with_real_data():
    """Test Agent 3 with real data from leads_raw.json"""
    
    print("=" * 80)
    print("TESTING AGENT 3 WITH REAL DATA")
    print("=" * 80)
    
    # Load leads from JSON
    all_leads = load_leads_from_json()
    
    if not all_leads:
        print("❌ No leads found. Please run the pipeline first to collect leads.")
        return
    
    # Display leads summary
    print("\n📊 LEADS SUMMARY:")
    print("-" * 80)
    print(f"{'#':<3} {'Name':<25} {'Company':<20} {'Role':<15} {'Segment':<8} {'Score':<5}")
    print("-" * 80)
    
    for i, lead in enumerate(all_leads, 1):
        print(f"{i:<3} {lead.get('name', 'Unknown')[:24]:<25} "
              f"{lead.get('company', 'Unknown')[:19]:<20} "
              f"{lead.get('role', 'Unknown')[:14]:<15} "
              f"{lead.get('segment', 'unknown'):<8} "
              f"{lead.get('score', 0):<5}")
    
    print("-" * 80)
    
    # Filter qualified leads (hot/warm)
    qualified_leads = filter_qualified_leads(all_leads, segment_filter=['hot', 'warm'])
    
    if not qualified_leads:
        print("\n⚠️ No qualified leads found (hot/warm)")
        
        # Show status distribution
        status_counts = {}
        for lead in all_leads:
            status = lead.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("\nStatus distribution:")
        for status, count in status_counts.items():
            print(f"  - {status}: {count}")
        
        return
    
    print(f"\n✅ Found {len(qualified_leads)} qualified leads to process")
    
    # Prepare leads for writer
    leads_for_writer = prepare_leads_for_writer(qualified_leads)
    
    # Display leads to be processed
    print("\n📝 LEADS FOR EMAIL GENERATION:")
    print("-" * 80)
    for i, lead in enumerate(leads_for_writer, 1):
        print(f"{i}. {lead['name']} - {lead['role']} @ {lead['company']}")
        print(f"   Score: {lead['score']} | Segment: {lead['segment']}")
        print(f"   Email: {lead.get('email', 'Not found')}")
        if lead.get('notes'):
            print(f"   Context: {lead['notes'][:100]}...")
        print()
    
    # Create writer agent
    print("\n🤖 Initializing Writer Agent...")
    try:
        writer = create_writer_agent()
        print("✅ Writer agent created successfully")
    except Exception as e:
        print(f"❌ Failed to create writer agent: {e}")
        return
    
    # Create write task
    print("\n📝 Creating write task...")
    
    # Use the original campaign context if available, otherwise create a default
    campaign_prompt = "Reach out to CTOs of AI startups in Berlin that raised funding"
    
    # Try to get campaign from first lead if available
    if qualified_leads and qualified_leads[0].get('campaign_id'):
        campaign_prompt = f"AI startups in Berlin that raised recent funding (Campaign: {qualified_leads[0].get('campaign_id')})"
    
    try:
        write_task = create_write_task(
            writer,
            campaign_prompt,
            json.dumps(leads_for_writer, ensure_ascii=False, indent=2)
        )
        print("✅ Write task created successfully")
    except Exception as e:
        print(f"❌ Failed to create write task: {e}")
        return
    
    # Create crew
    print("\n🚀 Starting email generation crew...")
    print("=" * 80)
    
    crew = Crew(
        agents=[writer],
        tasks=[write_task],
        process=Process.sequential,
        verbose=True
    )
    
    # Execute
    try:
        print("\nGENERATING PERSONALIZED EMAILS...\n")
        
        result = crew.kickoff()
        
        # Parse results
        result_str = str(result)
        match = re.search(r'\[.*\]', result_str, re.DOTALL)
        
        if match:
            try:
                emails = json.loads(match.group(0))
                
                print("\n" + "=" * 80)
                print("✅ EMAILS GENERATED SUCCESSFULLY")
                print("=" * 80)
                print(f"📊 Generated {len(emails)} personalized emails")
                
                # Display emails
                print("\n" + "=" * 80)
                print("EMAIL PREVIEWS")
                print("=" * 80)
                
                for i, email in enumerate(emails, 1):
                    print(f"\n{'='*80}")
                    print(f"EMAIL #{i}")
                    print(f"{'='*80}")
                    print(f"📧 To: {email.get('lead_name')} ({email.get('company')})")
                    print(f"📧 Email: {email.get('lead_email', 'Not found')}")
                    print(f"🎯 Subject: {email.get('subject', 'No subject')}")
                    print(f"🔗 Personalization Hook: {email.get('personalization_hook', 'None')}")
                    print(f"🌍 Language: {email.get('language', 'english').upper()}")
                    print(f"\n📝 Body:\n{'-'*80}")
                    print(email.get('body', 'No body content'))
                    print(f"{'-'*80}")
                
                # Save results
                output_file = f"emails_generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                output_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", output_file
                )
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(emails, f, ensure_ascii=False, indent=2)
                
                print(f"\n💾 Emails saved to: {output_path}")
                
                # Validation
                print("\n" + "=" * 80)
                print("VALIDATION CHECKS")
                print("=" * 80)
                
                validation_results = validate_emails(emails)
                
                # Summary
                print("\n" + "=" * 80)
                print("SUMMARY")
                print("=" * 80)
                print(f"✅ Total emails generated: {len(emails)}")
                print(f"📧 Emails with valid addresses: {validation_results['valid_emails']}")
                print(f"🎯 Emails with personalization: {validation_results['personalized']}")
                print(f"🌍 Languages used: {', '.join(validation_results['languages'])}")
                
                return emails
                
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON response: {e}")
                print(f"\nRaw output (first 1000 chars):\n{result_str[:1000]}")
                return None
        else:
            print("❌ No JSON array found in response")
            print(f"\nRaw output (first 1000 chars):\n{result_str[:1000]}")
            return None
            
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        return None

def validate_emails(emails):
    """Validate generated emails"""
    
    results = {
        'valid_emails': 0,
        'personalized': 0,
        'languages': set(),
        'issues': []
    }
    
    for i, email in enumerate(emails, 1):
        issues = []
        
        # Check subject
        subject = email.get('subject', '')
        if not subject:
            issues.append("Missing subject")
        elif len(subject) > 100:
            issues.append(f"Subject too long ({len(subject)} chars)")
        
        # Check body
        body = email.get('body', '')
        if not body:
            issues.append("Missing body")
        else:
            line_count = len(body.split('\n'))
            if line_count > 8:
                issues.append(f"Body has {line_count} lines (should be 4-6)")
        
        # Check for forbidden words
        forbidden = ['synergy', 'leverage', 'circle back', 'touch base', 'hope this email finds you well']
        body_lower = body.lower()
        for word in forbidden:
            if word in body_lower:
                issues.append(f"Contains forbidden word: '{word}'")
        
        # Check personalization
        hook = email.get('personalization_hook', '')
        if hook and hook != 'None':
            results['personalized'] += 1
        else:
            issues.append("Missing personalization hook")
        
        # Check language
        lang = email.get('language', 'unknown')
        if lang in ['english', 'french', 'arabic']:
            results['languages'].add(lang)
        else:
            issues.append(f"Invalid language: {lang}")
        
        # Check email
        if email.get('lead_email') and email.get('lead_email') != 'Not found':
            results['valid_emails'] += 1
        
        if issues:
            results['issues'].append({
                'email': i,
                'to': email.get('lead_name', 'Unknown'),
                'issues': issues
            })
    
    # Display issues
    if results['issues']:
        print("\n⚠️ Issues found:")
        for issue in results['issues']:
            print(f"\n  Email #{issue['email']} - {issue['to']}:")
            for prob in issue['issues']:
                print(f"    - {prob}")
    else:
        print("\n✅ All emails passed basic validation!")
    
    results['languages'] = list(results['languages'])
    
    return results

def test_specific_lead(lead_index=None):
    """Test Agent 3 with a specific lead from the data"""
    
    print("=" * 80)
    print("TESTING AGENT 3 - SPECIFIC LEAD")
    print("=" * 80)
    
    # Load leads
    all_leads = load_leads_from_json()
    
    if not all_leads:
        print("❌ No leads found")
        return
    
    # Filter qualified leads
    qualified = filter_qualified_leads(all_leads, segment_filter=['hot', 'warm'])
    
    if not qualified:
        print("❌ No qualified leads found")
        return
    
    # Select lead
    if lead_index is None or lead_index >= len(qualified):
        print(f"\nAvailable leads (0-{len(qualified)-1}):")
        for i, lead in enumerate(qualified):
            print(f"  {i}. {lead['name']} - {lead['role']} @ {lead['company']}")
        
        try:
            lead_index = int(input("\nSelect lead index: "))
        except:
            print("Invalid selection")
            return
    
    selected_lead = qualified[lead_index]
    
    print(f"\n📝 Testing with lead:")
    print(f"  Name: {selected_lead['name']}")
    print(f"  Company: {selected_lead['company']}")
    print(f"  Role: {selected_lead['role']}")
    print(f"  Notes: {selected_lead.get('notes', 'None')}")
    
    # Prepare single lead
    leads_for_writer = prepare_leads_for_writer([selected_lead])
    
    # Create writer agent
    writer = create_writer_agent()
    
    campaign_prompt = "Reach out to CTOs of AI startups in Berlin that raised funding"
    
    write_task = create_write_task(
        writer,
        campaign_prompt,
        json.dumps(leads_for_writer, ensure_ascii=False, indent=2)
    )
    
    crew = Crew(
        agents=[writer],
        tasks=[write_task],
        process=Process.sequential,
        verbose=False
    )
    
    print("\n🚀 Generating email...\n")
    
    try:
        result = crew.kickoff()
        
        result_str = str(result)
        match = re.search(r'\[.*\]', result_str, re.DOTALL)
        
        if match:
            emails = json.loads(match.group(0))
            if emails:
                email = emails[0]
                print("\n" + "=" * 80)
                print("GENERATED EMAIL")
                print("=" * 80)
                print(f"Subject: {email.get('subject')}")
                print(f"\nBody:\n{email.get('body')}")
                print("\n" + "=" * 80)
                
                # Save to file
                output_file = f"email_{selected_lead['company'].replace(' ', '_')}.txt"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"To: {selected_lead['name']} <{selected_lead.get('email', '')}>\n")
                    f.write(f"Subject: {email.get('subject')}\n")
                    f.write(f"\n{email.get('body')}\n")
                
                print(f"\n💾 Email saved to: {output_file}")
                
                return email
        else:
            print("❌ No valid JSON in response")
            print(f"\nRaw output:\n{result_str[:500]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Agent 3 with real data")
    parser.add_argument(
        "--mode",
        choices=["all", "single"],
        default="all",
        help="Test mode: all (all qualified leads), single (specific lead)"
    )
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="Lead index for single mode"
    )
    
    args = parser.parse_args()
    
    # Check environment
    if not os.getenv("GROQ_API_KEY"):
        print("⚠️ Warning: GROQ_API_KEY not found in .env file")
        print("Make sure it's set before running the test")
    
    # Run test
    if args.mode == "single":
        test_specific_lead(args.index)
    else:
        test_writer_with_real_data()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)