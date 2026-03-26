import os
import sys
import json
import re
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class EmailQualityValidator:
    """Validates the quality of generated emails"""
    
    def __init__(self):
        self.forbidden_words = [
            'synergy', 'leverage', 'circle back', 'touch base', 
            'hope this email finds you well', 'revolutionize', 
            'disrupt', 'game-changer', 'paradigm shift'
        ]
        
        self.required_elements = [
            'personalization_hook',
            'soft_question',
            'low_friction_cta'
        ]
        
    def validate_email(self, email: Dict, lead: Dict = None) -> Dict:
        """Validate a single email against quality criteria"""
        
        results = {
            'email_id': email.get('lead_name', 'Unknown'),
            'company': email.get('company', 'Unknown'),
            'passed': True,
            'checks': {},
            'issues': [],
            'warnings': [],
            'score': 0  # 0-100
        }
        
        # Check 1: Personalization hook exists and is relevant
        hook = email.get('personalization_hook', '')
        if hook and hook != 'None':
            results['checks']['personalization'] = True
            results['score'] += 25
            
            # Check if hook matches lead context
            if lead:
                context_match = False
                context_items = [
                    lead.get('notes', ''),
                    lead.get('company', ''),
                    lead.get('funding', ''),
                    str(lead.get('score', ''))
                ]
                
                for item in context_items:
                    if item and hook.lower() in item.lower():
                        context_match = True
                        break
                
                if not context_match:
                    results['warnings'].append(f"Personalization hook may not match lead context: '{hook}'")
                    results['score'] -= 5
        else:
            results['checks']['personalization'] = False
            results['issues'].append("Missing personalization hook")
            results['score'] -= 25
        
        # Check 2: Subject line quality
        subject = email.get('subject', '')
        if subject:
            results['checks']['subject'] = True
            results['score'] += 15
            
            # Check subject length
            if len(subject) > 80:
                results['warnings'].append(f"Subject line too long: {len(subject)} chars (max 80)")
                results['score'] -= 3
            elif len(subject) < 10:
                results['warnings'].append(f"Subject line too short: {len(subject)} chars")
                results['score'] -= 2
            
            # Check if subject contains hook
            if hook and hook.lower() not in subject.lower():
                results['warnings'].append("Subject line doesn't reference personalization hook")
                results['score'] -= 5
        else:
            results['checks']['subject'] = False
            results['issues'].append("Missing subject line")
            results['score'] -= 15
        
        # Check 3: Body length and structure
        body = email.get('body', '')
        if body:
            results['checks']['body'] = True
            results['score'] += 20
            
            # Count words and lines
            word_count = len(body.split())
            line_count = len(body.split('\n'))
            
            # Check length
            if word_count > 150:
                results['warnings'].append(f"Email too long: {word_count} words (max 150)")
                results['score'] -= 5
            elif word_count < 50:
                results['warnings'].append(f"Email too short: {word_count} words (min 50)")
                results['score'] -= 3
            
            # Check line count
            if line_count > 10:
                results['warnings'].append(f"Too many lines: {line_count} (max 8-10)")
                results['score'] -= 3
            
            # Check for forbidden words
            found_forbidden = []
            body_lower = body.lower()
            for word in self.forbidden_words:
                if word in body_lower:
                    found_forbidden.append(word)
            
            if found_forbidden:
                results['issues'].append(f"Contains forbidden words: {', '.join(found_forbidden)}")
                results['score'] -= 10
            
            # Check for soft question
            question_patterns = [
                r'\?',  # Question mark
                r'would you', r'do you', r'are you', r'could you',
                r'curious', r'interested', r'open to', r'worth a'
            ]
            
            has_question = any(re.search(pattern, body_lower) for pattern in question_patterns)
            if has_question:
                results['checks']['soft_question'] = True
                results['score'] += 10
            else:
                results['warnings'].append("No question found in email")
                results['score'] -= 5
            
            # Check for CTA
            cta_patterns = [
                r'call', r'chat', r'meeting', r'discuss', r'explore',
                r'quick', r'15 minutes', r'20 minutes', r'coffee'
            ]
            
            has_cta = any(re.search(pattern, body_lower) for pattern in cta_patterns)
            if has_cta:
                results['checks']['cta'] = True
                results['score'] += 10
            else:
                results['warnings'].append("No clear CTA found")
                results['score'] -= 5
            
        else:
            results['checks']['body'] = False
            results['issues'].append("Missing email body")
            results['score'] -= 20
        
        # Check 4: Language detection
        lang = email.get('language', 'unknown')
        if lang in ['english', 'french', 'arabic']:
            results['checks']['language'] = True
            results['score'] += 5
        else:
            results['warnings'].append(f"Invalid language: {lang}")
            results['score'] -= 3
        
        # Check 5: Email address (if available)
        lead_email = email.get('lead_email', '')
        if lead_email and lead_email != 'Not found':
            # Basic email validation
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if re.match(email_pattern, lead_email):
                results['checks']['email_valid'] = True
                results['score'] += 5
            else:
                results['warnings'].append(f"Invalid email format: {lead_email}")
        
        # Determine final pass/fail
        results['passed'] = len(results['issues']) == 0 and results['score'] >= 70
        
        return results
    
    def validate_batch(self, emails: List[Dict], leads: List[Dict] = None) -> Dict:
        """Validate a batch of emails"""
        
        results = {
            'total': len(emails),
            'passed': 0,
            'failed': 0,
            'average_score': 0,
            'details': [],
            'summary': {
                'personalization_hooks': 0,
                'questions': 0,
                'ctas': 0,
                'forbidden_words_used': [],
                'language_distribution': {}
            }
        }
        
        total_score = 0
        
        for i, email in enumerate(emails):
            lead = leads[i] if leads and i < len(leads) else None
            validation = self.validate_email(email, lead)
            results['details'].append(validation)
            
            if validation['passed']:
                results['passed'] += 1
            else:
                results['failed'] += 1
            
            total_score += validation['score']
            
            # Update summary statistics
            if validation['checks'].get('personalization', False):
                results['summary']['personalization_hooks'] += 1
            
            if validation['checks'].get('soft_question', False):
                results['summary']['questions'] += 1
            
            if validation['checks'].get('cta', False):
                results['summary']['ctas'] += 1
            
            lang = email.get('language', 'unknown')
            results['summary']['language_distribution'][lang] = \
                results['summary']['language_distribution'].get(lang, 0) + 1
        
        if results['total'] > 0:
            results['average_score'] = total_score / results['total']
        
        return results

def test_quality_with_real_emails():
    """Test the quality of generated emails"""
    
    print("=" * 80)
    print("EMAIL QUALITY VALIDATION TEST")
    print("=" * 80)
    
    # Sample emails from your output
    test_emails = [
        {
            "lead_name": "Brad Heller",
            "lead_email": "amalie.holland1@gmail.com",
            "company": "Tower",
            "subject": "Congrats on Tower’s €5.5M round – quick thought on data‑engineer pipelines",
            "body": "Congrats on Tower’s €5.5 M raise to power the last‑mile platform for data engineers.\nWe’ve built a lightweight MLOps layer that plugs directly into existing pipelines, shaving hours of manual setup.\nGiven your focus on scaling engineer productivity, it could keep the momentum from the new funding.\nWould you have 20 minutes next week to explore if it fits your roadmap?\nAlex Reed | ScaleAI Labs",
            "language": "english",
            "personalization_hook": "Tower’s €5.5 M funding for a last‑mile platform for data engineers"
        },
        {
            "lead_name": "Armenak Mayalian",
            "lead_email": "freepress@wpfc.org",
            "company": "Parloa",
            "subject": "Parloa’s $120M Series C – ideas on scaling voice‑AI reliability",
            "body": "Seeing Parloa’s $120 M Series C to reinvent voice AI is impressive.\nWe help teams add real‑time health checks to thousands of agents without code changes.\nThat could let your engineers focus on new features while the platform stays stable at unicorn scale.\nCan we set aside 20 minutes to see if it aligns with your next release?\nAlex Reed | ScaleAI Labs",
            "language": "english",
            "personalization_hook": "Parloa’s $120 M Series C funding to reinvent voice AI"
        },
        {
            "lead_name": "Roland Busch",
            "lead_email": "roland.busch@siemens.com",
            "company": "Cognee",
            "subject": "Cognee’s $7.5M funding – quick note on long‑term memory for agents",
            "body": "Congrats on Cognee’s $7.5 M round to build long‑term memory for AI agents.\nWe’ve released an open‑source cache layer that lets agents retrieve past interactions instantly.\nIntegrating it could accelerate your memory‑graph rollout without re‑architecting core services.\nDo you have 20 minutes next week to discuss a lightweight integration?\nAlex Reed | ScaleAI Labs",
            "language": "english",
            "personalization_hook": "Cognee’s $7.5 M funding for long‑term memory for AI agents"
        },
        {
            "lead_name": "Ziar Khosrawi",
            "lead_email": "ziar@bounti.co",
            "company": "Bounti",
            "subject": "Bounti’s €4M seed – thoughts on AI at the frontline",
            "body": "Congrats on Bounti’s €4 M seed to boost AI for frontline workers.\nOur edge‑to‑cloud ingestion toolkit lets you collect and label data from handheld devices in minutes.\nThat could speed up model training for the on‑site use cases you’re targeting.\nWould a 20‑minute chat help you evaluate a quick pilot?\nAlex Reed | ScaleAI Labs",
            "language": "english",
            "personalization_hook": "Bounti’s €4 M seed funding for AI platform for frontline workers"
        },
        {
            "lead_name": "Tobias Siwonia",
            "lead_email": "tobias@peec.ai",
            "company": "Peec AI",
            "subject": "Peec AI’s $21M Series A – quick idea on generative engine scaling",
            "body": "Impressed by Peec AI’s $21 M Series A to power generative engine optimization.\nWe provide a scheduler that auto‑balances workloads across GPUs, cutting compute spend by up to 30 %.\nIt could let your engineers push more experiments while staying within budget.\nAre you open to a 20‑minute call to explore a fit?\nAlex Reed | ScaleAI Labs",
            "language": "english",
            "personalization_hook": "Peec AI’s $21 M Series A funding for generative engine optimization"
        }
    ]
    
    # Corresponding leads for context
    test_leads = [
        {"company": "Tower", "notes": "Raised €5.5 million in March 2026", "score": 100},
        {"company": "Parloa", "notes": "AI unicorn, raises $120M in Series C", "score": 95},
        {"company": "Cognee", "notes": "$7.5 million for long-term memory for AI agents", "score": 100},
        {"company": "Bounti", "notes": "€4 million seed funding for AI platform", "score": 100},
        {"company": "Peec AI", "notes": "$21 Million Series A for generative engine optimization", "score": 100}
    ]
    
    print(f"\n📊 Testing {len(test_emails)} emails...")
    
    # Create validator and run tests
    validator = EmailQualityValidator()
    results = validator.validate_batch(test_emails, test_leads)
    
    # Display results
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    
    print(f"\n📈 Summary Statistics:")
    print(f"  Total emails: {results['total']}")
    print(f"  ✅ Passed: {results['passed']} ({results['passed']/results['total']*100:.1f}%)")
    print(f"  ❌ Failed: {results['failed']} ({results['failed']/results['total']*100:.1f}%)")
    print(f"  ⭐ Average quality score: {results['average_score']:.1f}/100")
    
    print(f"\n📊 Quality Metrics:")
    print(f"  🎯 Personalization hooks: {results['summary']['personalization_hooks']}/{results['total']}")
    print(f"  ❓ Soft questions: {results['summary']['questions']}/{results['total']}")
    print(f"  🚀 Clear CTAs: {results['summary']['ctas']}/{results['total']}")
    
    print(f"\n🌍 Language Distribution:")
    for lang, count in results['summary']['language_distribution'].items():
        print(f"  {lang}: {count}")
    
    # Display detailed results
    print("\n" + "=" * 80)
    print("DETAILED EMAIL ANALYSIS")
    print("=" * 80)
    
    for i, (email, validation) in enumerate(zip(test_emails, results['details']), 1):
        print(f"\n{'='*80}")
        print(f"EMAIL #{i} - {validation['company']}")
        print(f"{'='*80}")
        
        # Status
        status = "✅ PASSED" if validation['passed'] else "❌ FAILED"
        print(f"Status: {status} | Score: {validation['score']:.0f}/100")
        
        # Subject
        print(f"\n📧 Subject: {email.get('subject', 'MISSING')[:80]}")
        
        # Personalization
        hook = email.get('personalization_hook', 'None')
        print(f"\n🎯 Personalization Hook: {hook}")
        


        
        # Issues
        if validation['issues']:
            print(f"\n❌ Issues:")
            for issue in validation['issues']:
                print(f"  • {issue}")
        
        # Warnings
        if validation['warnings']:
            print(f"\n⚠️ Warnings:")
            for warning in validation['warnings']:
                print(f"  • {warning}")
        
        # Score breakdown
        print(f"\n📊 Score Breakdown:")
        print(f"  Personalization: {25 if validation['checks'].get('personalization', False) else 0}/25")
        print(f"  Subject: {15 if validation['checks'].get('subject', False) else 0}/15")
        print(f"  Body: {20 if validation['checks'].get('body', False) else 0}/20")
        print(f"  Question: {10 if validation['checks'].get('soft_question', False) else 0}/10")
        print(f"  CTA: {10 if validation['checks'].get('cta', False) else 0}/10")
        print(f"  Language: {5 if validation['checks'].get('language', False) else 0}/5")
        print(f"  Email: {5 if validation['checks'].get('email_valid', False) else 0}/5")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if results['average_score'] >= 90:
        print("✅ Excellent quality! Emails are highly personalized and well-structured.")
        print("   Consider A/B testing different subject line formats to optimize open rates.")
    elif results['average_score'] >= 75:
        print("👍 Good quality with minor improvements needed:")
        if results['summary']['questions'] < results['total']:
            print("   • Add soft questions to increase engagement")
        if results['summary']['ctas'] < results['total']:
            print("   • Include clear, low-friction CTAs")
        if any(not v['checks'].get('personalization') for v in results['details']):
            print("   • Ensure every email has a strong personalization hook")
    else:
        print("⚠️ Quality issues detected. Focus on:")
        print("   • Stronger personalization hooks referencing specific company news")
        print("   • Shorter, more concise emails (aim for 80-100 words)")
        print("   • Natural questions that invite conversation")
        print("   • Clear but low-pressure CTAs")
    
    # Save full results
    output_file = f"email_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n💾 Full quality report saved to: {output_file}")
    
    return results

def generate_improvement_suggestions():
    """Generate suggestions for improving email quality"""
    
    print("\n" + "=" * 80)
    print("IMPROVEMENT SUGGESTIONS")
    print("=" * 80)
    
    suggestions = [
        {
            "area": "Subject Lines",
            "current": "Good - all reference funding rounds",
            "improvement": "Test different formats: question-based, curiosity-gap, or problem-focused subjects"
        },
        {
            "area": "Personalization Depth",
            "current": "Excellent - all reference specific funding amounts",
            "improvement": "Consider adding second-layer personalization (tech stack, hiring posts, specific product features)"
        },
        {
            "area": "Body Length",
            "current": "5-6 lines, ~100-120 words",
            "improvement": "Already optimal. Maintain this conciseness."
        },
        {
            "area": "Value Proposition",
            "current": "Generic MLOps/infrastructure solutions",
            "improvement": "Could be more specific to each company's unique pain point (voice AI for Parloa, data pipelines for Tower)"
        },
        {
            "area": "CTA",
            "current": "20-minute calls",
            "improvement": "Consider varying CTAs: 'Quick question', 'Thoughts?', 'Worth exploring?'"
        },
        {
            "area": "Email Addresses",
            "current": "Some emails are personal or incorrect (amalie.holland1@gmail.com for Brad Heller)",
            "improvement": "Verify email addresses before sending. Use contact finder tools to get professional emails."
        }
    ]
    
    for suggestion in suggestions:
        print(f"\n📌 {suggestion['area']}:")
        print(f"   Current: {suggestion['current']}")
        print(f"   💡 Improvement: {suggestion['improvement']}")
    
    # Email validation suggestion
    print("\n" + "=" * 80)
    print("CRITICAL ISSUE TO FIX")
    print("=" * 80)
    print("\n⚠️ Email address issue detected:")
    print("   Brad Heller's email is 'amalie.holland1@gmail.com' (incorrect)")
    print("   Armenak Mayalian's email is 'freepress@wpfc.org' (likely wrong)")
    print("\n🔧 Solution:")
    print("   1. Implement email verification before sending")
    print("   2. Use multiple email finding sources (FTL, Apollo, Hunter)")
    print("   3. Validate email format and domain")
    print("   4. Consider using email verification APIs")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test email quality for Agent 3")
    parser.add_argument(
        "--mode",
        choices=["validate", "suggestions", "all"],
        default="all",
        help="Test mode: validate (quality check), suggestions (improvements), all (both)"
    )
    
    args = parser.parse_args()
    
    if args.mode in ["validate", "all"]:
        test_quality_with_real_emails()
    
    if args.mode in ["suggestions", "all"]:
        generate_improvement_suggestions()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)