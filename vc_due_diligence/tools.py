"""Custom tools for the Due Diligence Pipeline.

Provides HTML report generation, financial charts, and infographic creation.
"""

import logging
import io
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from datetime import datetime
from google.adk.tools import ToolContext
from google.genai import types, Client

logger = logging.getLogger("DueDiligencePipeline")


def get_user_email_from_context(session_id: str = "") -> str:
    """Get user email from Redis via kong-proxy's per-session storage.

    Args:
        session_id: The ADK session_id to look up the email for.

    Returns:
        User email from Redis lookup, or empty string if not available.
    """
    try:
        import sys
        if '/app' in sys.path or '/workspace' in sys.path:
            try:
                from server import get_current_user_email
                email = get_current_user_email(session_id=session_id)
                if email:
                    logger.info(f"Retrieved user email from Redis for session {session_id}: {email}")
                    return email
            except ImportError:
                logger.debug("Custom server module not available, email retrieval skipped")
    except Exception as e:
        logger.debug(f"Could not retrieve user email from context: {e}")

    return ""

# Create _outputs directory for generated files (underscore prefix to avoid ADK treating it as agent)
OUTPUTS_DIR = Path(__file__).parent / "_outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)


async def send_email_with_pdf(
    recipient_email: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    company_name: str = "Company"
) -> dict:
    """Send PDF report via email using SMTP.

    Args:
        recipient_email: Email address to send the report to
        pdf_bytes: PDF file content as bytes
        pdf_filename: Name of the PDF file
        company_name: Company name for email subject

    Returns:
        dict with status and message
    """
    try:
        # Get SMTP configuration from environment variables
        smtp_host = os.getenv("SMTP_HOST", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "25"))
        smtp_use_auth = os.getenv("SMTP_USE_AUTH", "false").lower() == "true"
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        smtp_from_email = os.getenv("SMTP_FROM_EMAIL", "info@bionicaisolutions.com")
        smtp_from_name = os.getenv("SMTP_FROM_NAME", "VC Due Diligence AI")

        # Only check credentials if authentication is required
        if smtp_use_auth and (not smtp_user or not smtp_password):
            logger.warning("SMTP authentication enabled but credentials not configured. Email not sent.")
            return {
                "status": "skipped",
                "message": "SMTP credentials not configured. Please set SMTP_USER and SMTP_PASSWORD environment variables."
            }

        # Validate email address
        if not recipient_email or "@" not in recipient_email:
            logger.error(f"Invalid email address: {recipient_email}")
            return {
                "status": "error",
                "message": f"Invalid email address: {recipient_email}"
            }

        # Create email message
        msg = MIMEMultipart()
        msg['From'] = f"{smtp_from_name} <{smtp_from_email}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"Investment Due Diligence Report - {company_name}"

        # Email body
        body = f"""
Dear Investor,

Please find attached the comprehensive due diligence report for {company_name}.

This AI-generated report includes:
- Company Research & Market Analysis
- Financial Modeling & Projections
- Risk Assessment
- Investment Recommendation

The report was generated specifically for your review.

Best regards,
VC Due Diligence AI Team

---
This is an automated message. Please do not reply to this email.
"""
        msg.attach(MIMEText(body, 'plain'))

        # Attach PDF
        pdf_attachment = MIMEBase('application', 'pdf')
        pdf_attachment.set_payload(pdf_bytes)
        encoders.encode_base64(pdf_attachment)
        pdf_attachment.add_header(
            'Content-Disposition',
            f'attachment; filename="{pdf_filename}"'
        )
        msg.attach(pdf_attachment)

        # Send email
        logger.info(f"Sending email to {recipient_email} via {smtp_host}:{smtp_port} (auth: {smtp_use_auth})")

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            # Only use STARTTLS and authentication if required
            if smtp_use_auth:
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(f"Email sent successfully to {recipient_email}")
        return {
            "status": "success",
            "message": f"Report emailed successfully to {recipient_email}",
            "recipient": recipient_email
        }

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check credentials.")
        return {
            "status": "error",
            "message": "Email authentication failed. Please check SMTP credentials."
        }
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {e}")
        return {
            "status": "error",
            "message": f"Failed to send email: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return {
            "status": "error",
            "message": f"Failed to send email: {str(e)}"
        }


async def generate_financial_chart(
    company_name: str,
    current_arr: float,
    bear_rates: str,
    base_rates: str,
    bull_rates: str,
    tool_context: ToolContext
) -> dict:
    """Generate a revenue projection chart and save as ADK artifact.

    Args:
        company_name: Name of the company being analyzed
        current_arr: Current ARR in millions (e.g., 1.2 for $1.2M)
        bear_rates: Comma-separated YoY growth rates for bear case
        base_rates: Comma-separated YoY growth rates for base case
        bull_rates: Comma-separated YoY growth rates for bull case
        tool_context: ADK tool context for artifact saving

    Returns:
        dict with status and artifact info
    """
    # Store company name in session state for display in the session list sidebar
    tool_context.state["session_name"] = company_name

    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')

        # Parse growth rates
        bear = [float(x.strip()) for x in bear_rates.split(",")]
        base = [float(x.strip()) for x in base_rates.split(",")]
        bull = [float(x.strip()) for x in bull_rates.split(",")]
        
        # Calculate projections
        years = list(range(2025, 2025 + len(base) + 1))
        
        def project_arr(start, rates):
            arr = [start]
            for rate in rates:
                arr.append(arr[-1] * rate)
            return arr
        
        bear_arr = project_arr(current_arr, bear)
        base_arr = project_arr(current_arr, base)
        bull_arr = project_arr(current_arr, bull)
        
        # Create professional chart
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.plot(years, bear_arr, 'o-', color='#dc2626', linewidth=2, markersize=8, label='Bear Case')
        ax.plot(years, base_arr, 's-', color='#1a365d', linewidth=3, markersize=10, label='Base Case')
        ax.plot(years, bull_arr, '^-', color='#16a34a', linewidth=2, markersize=8, label='Bull Case')
        ax.fill_between(years, bear_arr, bull_arr, alpha=0.1, color='#1a365d')
        
        ax.set_title(f'{company_name} - Revenue Projection Analysis', fontsize=16, fontweight='bold', color='#1a365d')
        ax.set_xlabel('Year', fontsize=12)
        ax.set_ylabel('ARR ($ Millions)', fontsize=12)
        ax.legend(loc='upper left', fontsize=11)
        
        for x, y in zip(years, base_arr):
            ax.annotate(f'${y:.1f}M', (x, y), textcoords="offset points", 
                       xytext=(0, 10), ha='center', fontsize=9, color='#1a365d')
        
        ax.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_bytes = buffer.read()
        plt.close()
        
        # Save as ADK artifact (MUST await)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_name = f"revenue_chart_{timestamp}.png"
        chart_artifact = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        
        version = await tool_context.save_artifact(filename=artifact_name, artifact=chart_artifact)
        logger.info(f"Saved chart artifact: {artifact_name} (version {version})")
        
        # Also save to outputs folder
        filepath = OUTPUTS_DIR / artifact_name
        filepath.write_bytes(image_bytes)
        
        return {
            "status": "success",
            "message": f"Chart saved as '{artifact_name}' - view in Artifacts tab",
            "artifact": artifact_name,
            "version": version,
            "summary": {
                "year_5_bear": f"${bear_arr[-1]:.1f}M",
                "year_5_base": f"${base_arr[-1]:.1f}M",
                "year_5_bull": f"${bull_arr[-1]:.1f}M"
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return {"status": "error", "message": str(e)}


async def generate_html_report(
    report_data: str,
    tool_context: ToolContext
) -> dict:
    """Generate a professional HTML investment report.

    Args:
        report_data: The investor memo content to format as HTML
        tool_context: ADK tool context for artifact saving

    Returns:
        dict with status and artifact info
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""Generate a professional investment due diligence report in HTML format.

**IMPORTANT: Use this exact date: {current_date}**

Style it like a McKinsey or Goldman Sachs investment memo with:
- Clean, professional design with dark blue (#1a365d) and gold (#d4af37) colors
- Executive summary at the top with DATE: {current_date}
- Clear section headers with good typography
- Data tables for metrics
- Print-friendly layout

DATA TO FORMAT:
{report_data}

SECTIONS TO INCLUDE:
1. Executive Summary (Date: {current_date})
2. Company Overview
3. Market Opportunity
4. Financial Analysis
5. Risk Assessment
6. Investment Recommendation

Generate complete, valid HTML with embedded CSS."""

    try:
        client = Client()
        response = await client.aio.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )

        html_content = response.text

        # Clean up markdown wrapping if present
        if "```html" in html_content:
            start = html_content.find("```html") + 7
            end = html_content.rfind("```")
            html_content = html_content[start:end].strip()
        elif "```" in html_content:
            start = html_content.find("```") + 3
            end = html_content.rfind("```")
            html_content = html_content[start:end].strip()

        # Save as ADK artifact (MUST await)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_name = f"investment_report_{timestamp}.html"
        html_artifact = types.Part.from_bytes(
            data=html_content.encode('utf-8'),
            mime_type="text/html"
        )
        
        version = await tool_context.save_artifact(filename=artifact_name, artifact=html_artifact)
        logger.info(f"Saved HTML artifact: {artifact_name} (version {version})")

        # Also save to outputs folder
        filepath = OUTPUTS_DIR / artifact_name
        filepath.write_text(html_content, encoding='utf-8')
        
        return {
            "status": "success",
            "message": f"Report saved as '{artifact_name}' - view in Artifacts tab",
            "artifact": artifact_name,
            "version": version
        }

    except Exception as e:
        logger.error(f"Error generating HTML report: {e}")
        return {"status": "error", "message": str(e)}


async def generate_infographic(
    data_summary: str,
    tool_context: ToolContext
) -> dict:
    """Generate an investment infographic using Gemini's image generation.

    Args:
        data_summary: Key metrics and data to visualize
        tool_context: ADK tool context for artifact saving

    Returns:
        dict with status and artifact info
    """
    prompt = f"""Create a professional investment infographic.

Style: Clean, modern, investment banking aesthetic
Colors: Dark blue (#1a365d) primary, gold (#d4af37) accent, white background

Content to visualize:
{data_summary}

Include:
1. Company name prominently at top
2. Key metrics in large, bold numbers
3. Market size visualization
4. Risk score indicator (1-10 scale)
5. Investment recommendation badge

Make it look like a Goldman Sachs one-pager. Professional, data-rich."""

    try:
        client = Client()
        response = await client.aio.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        )

        # Look for image in response
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type
                
                # Save as ADK artifact (MUST await)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = "png" if "png" in mime_type else "jpg"
                artifact_name = f"infographic_{timestamp}.{ext}"
                
                image_artifact = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                version = await tool_context.save_artifact(filename=artifact_name, artifact=image_artifact)
                logger.info(f"Saved infographic artifact: {artifact_name} (version {version})")
                
                # Also save to outputs folder
                filepath = OUTPUTS_DIR / artifact_name
                filepath.write_bytes(image_bytes)
                
                return {
                    "status": "success",
                    "message": f"Infographic saved as '{artifact_name}' - view in Artifacts tab",
                    "artifact": artifact_name,
                    "version": version
                }

        return {
            "status": "partial",
            "message": "Image generation not available",
            "description": response.text if response.text else "No content"
        }

    except Exception as e:
        logger.error(f"Error generating infographic: {e}")
        return {"status": "error", "message": str(e)}


async def generate_pdf_report(
    company_info: str,
    market_analysis: str,
    financial_model: str,
    risk_assessment: str,
    investor_memo: str,
    tool_context: ToolContext,
    user_email: str = ""
) -> dict:
    """Generate a comprehensive PDF report with all artifacts and agent outputs.

    Args:
        company_info: Output from CompanyResearchAgent
        market_analysis: Output from MarketAnalysisAgent
        financial_model: Output from FinancialModelingAgent
        risk_assessment: Output from RiskAssessmentAgent
        investor_memo: Output from InvestorMemoAgent
        tool_context: ADK tool context for artifact saving
        user_email: Email address to send the report to (optional, from Kong X-Consumer-Username header)

    Returns:
        dict with status, artifact info, and email status
    """
    try:
        from weasyprint import HTML, CSS
        from datetime import datetime
        import base64
        import markdown

        current_date = datetime.now().strftime("%B %d, %Y")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # If user_email not provided as parameter, look up from Redis using session_id
        if not user_email or not user_email.strip():
            current_session_id = tool_context.session.id
            user_email = get_user_email_from_context(session_id=current_session_id)
            if user_email:
                logger.info(f"Using user email from Redis for session {current_session_id}: {user_email}")
            else:
                logger.info(f"No user email available for session {current_session_id} - PDF will be generated but not emailed")

        # Extract company name from investor memo for email subject and report title
        company_name = "Investment Opportunity"
        try:
            first_lines = investor_memo.split('\n')[:10]
            for line in first_lines:
                if line.strip() and not line.startswith('#'):
                    company_name = line.strip()[:50]
                    break
        except Exception:
            pass

        # Find the most recent artifacts in the outputs directory
        chart_files = sorted(OUTPUTS_DIR.glob("revenue_chart_*.png"), reverse=True)
        infographic_files = sorted(OUTPUTS_DIR.glob("infographic_*.*"), reverse=True)

        chart_path = chart_files[0] if chart_files else None
        infographic_path = infographic_files[0] if infographic_files else None

        # Encode images as base64 for embedding
        chart_base64 = ""
        infographic_base64 = ""

        if chart_path and chart_path.exists():
            with open(chart_path, 'rb') as f:
                chart_base64 = base64.b64encode(f.read()).decode()

        if infographic_path and infographic_path.exists():
            with open(infographic_path, 'rb') as f:
                infographic_base64 = base64.b64encode(f.read()).decode()

        # Build comprehensive HTML with all sections
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Comprehensive Investment Due Diligence Report - {company_name}</title>
    <style>
        @page {{
            size: A4;
            margin: 15mm;
            @bottom-center {{
                content: "Page " counter(page) " of " counter(pages);
                font-size: 9pt;
                color: #666;
            }}
        }}

        :root {{
            --primary-blue: #1a365d;
            --accent-gold: #d4af37;
            --text-gray: #333333;
            --light-gray: #f4f4f4;
            --border-color: #e2e8f0;
        }}

        body {{
            font-family: "Helvetica", "Arial", sans-serif;
            line-height: 1.6;
            color: var(--text-gray);
            margin: 0;
            padding: 0;
        }}

        .cover-page {{
            page-break-after: always;
            text-align: center;
            padding-top: 100px;
        }}

        .cover-page h1 {{
            font-size: 36pt;
            color: var(--primary-blue);
            margin-bottom: 20px;
        }}

        .cover-page .subtitle {{
            font-size: 18pt;
            color: var(--accent-gold);
            margin-bottom: 40px;
        }}

        .cover-page .date {{
            font-size: 14pt;
            color: #666;
            margin-top: 50px;
        }}

        .confidential-banner {{
            background-color: #8b0000;
            color: white;
            padding: 15px;
            text-align: center;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 30px;
        }}

        h1, h2, h3 {{
            color: var(--primary-blue);
        }}

        h1 {{
            font-size: 24pt;
            border-bottom: 3px solid var(--accent-gold);
            padding-bottom: 10px;
            margin-top: 40px;
            page-break-after: avoid;
        }}

        h2 {{
            font-size: 18pt;
            border-left: 5px solid var(--accent-gold);
            padding-left: 15px;
            margin-top: 30px;
            page-break-after: avoid;
        }}

        h3 {{
            font-size: 14pt;
            margin-top: 20px;
            page-break-after: avoid;
        }}

        .section {{
            page-break-inside: avoid;
            margin-bottom: 30px;
        }}

        .section-content {{
            background-color: #f8fafc;
            padding: 20px;
            border-left: 4px solid var(--primary-blue);
            margin: 15px 0;
        }}

        .artifact-container {{
            page-break-inside: avoid;
            margin: 20px auto;
            text-align: center;
            max-width: 100%;
        }}

        .artifact-container img {{
            max-width: 100%;
            max-height: 650px;
            height: auto;
            width: auto;
            object-fit: contain;
            border: 1px solid var(--border-color);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: block;
            margin: 0 auto;
        }}

        .chart-container {{
            page-break-before: auto;
            page-break-after: auto;
            page-break-inside: avoid;
            margin: 30px auto;
            padding: 20px 0;
        }}

        .chart-container img {{
            max-width: 90%;
            max-height: 500px;
            height: auto;
            width: auto;
            object-fit: contain;
        }}

        .infographic-container {{
            page-break-before: always;
            page-break-inside: avoid;
            margin: 30px auto;
            padding: 20px 0;
        }}

        .infographic-container img {{
            max-width: 85%;
            max-height: 700px;
            height: auto;
            width: auto;
            object-fit: contain;
        }}

        .artifact-caption {{
            font-size: 10pt;
            color: #666;
            font-style: italic;
            margin-top: 10px;
        }}

        pre {{
            background-color: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            white-space: pre-wrap;
            font-size: 10pt;
        }}

        .section-content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 10pt;
        }}

        .section-content th {{
            background-color: var(--primary-blue);
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}

        .section-content td {{
            padding: 10px;
            border-bottom: 1px solid var(--border-color);
        }}

        .section-content tr:nth-child(even) {{
            background-color: #f9fafb;
        }}

        .section-content ul, .section-content ol {{
            margin: 15px 0;
            padding-left: 30px;
        }}

        .section-content li {{
            margin: 8px 0;
            line-height: 1.6;
        }}

        .section-content p {{
            margin: 12px 0;
            line-height: 1.8;
        }}

        .section-content strong {{
            color: var(--primary-blue);
            font-weight: 600;
        }}

        .section-content em {{
            color: #555;
        }}

        .section-content h4, .section-content h5, .section-content h6 {{
            color: var(--primary-blue);
            margin-top: 15px;
            margin-bottom: 10px;
        }}

        .toc {{
            page-break-after: always;
        }}

        .toc h2 {{
            text-align: center;
        }}

        .toc ul {{
            list-style: none;
            padding-left: 0;
        }}

        .toc li {{
            margin: 10px 0;
            padding: 10px;
            border-bottom: 1px solid var(--border-color);
        }}

        .page-break {{
            page-break-before: always;
        }}
    </style>
</head>
<body>
    <!-- Cover Page -->
    <div class="cover-page">
        <h1>Investment Due Diligence Report - {company_name}</h1>
        <div class="subtitle">Comprehensive Analysis & Recommendation</div>
        <div class="date">{current_date}</div>
        <div style="margin-top: 100px; font-size: 12pt; color: #8b0000; font-weight: bold;">
            HIGHLY CONFIDENTIAL<br>
            FOR INVESTMENT COMMITTEE USE ONLY
        </div>
    </div>

    <!-- Table of Contents -->
    <div class="toc">
        <h2>Table of Contents</h2>
        <ul>
            <li><strong>1.</strong> Executive Summary (Investor Memo)</li>
            <li><strong>2.</strong> Company Research Findings</li>
            <li><strong>3.</strong> Market Analysis</li>
            <li><strong>4.</strong> Financial Modeling & Projections</li>
            <li><strong>5.</strong> Risk Assessment</li>
            <li><strong>6.</strong> Visual Artifacts</li>
            <li><strong>7.</strong> Appendices</li>
        </ul>
    </div>

    <div class="confidential-banner">
        Highly Confidential - Investment Committee Use Only
    </div>

    <!-- Section 1: Investor Memo -->
    <h1>1. Executive Summary</h1>
    <div class="section-content">
        {markdown.markdown(investor_memo, extensions=['extra', 'nl2br'])}
    </div>

    <!-- Section 2: Company Research -->
    <div class="page-break"></div>
    <h1>2. Company Research Findings</h1>
    <h2>Detailed Company Intelligence</h2>
    <div class="section-content">
        {markdown.markdown(company_info, extensions=['extra', 'nl2br', 'tables'])}
    </div>

    <!-- Section 3: Market Analysis -->
    <div class="page-break"></div>
    <h1>3. Market Analysis</h1>
    <h2>Market Sizing & Competitive Landscape</h2>
    <div class="section-content">
        {markdown.markdown(market_analysis, extensions=['extra', 'nl2br', 'tables'])}
    </div>

    <!-- Section 4: Financial Model -->
    <div class="page-break"></div>
    <h1>4. Financial Modeling & Projections</h1>
    <h2>Revenue Projections & Unit Economics</h2>
    <div class="section-content">
        {markdown.markdown(financial_model, extensions=['extra', 'nl2br', 'tables'])}
    </div>

    {f'''
    <div class="chart-container">
        <h3>Revenue Projection Chart</h3>
        <div class="artifact-container">
            <img src="data:image/png;base64,{chart_base64}" alt="Revenue Projections">
        </div>
        <div class="artifact-caption">Bear, Base, and Bull case revenue projections over 5 years</div>
    </div>
    ''' if chart_base64 else ''}

    <!-- Section 5: Risk Assessment -->
    <div class="page-break"></div>
    <h1>5. Risk Assessment</h1>
    <h2>Comprehensive Risk Analysis</h2>
    <div class="section-content">
        {markdown.markdown(risk_assessment, extensions=['extra', 'nl2br', 'tables'])}
    </div>

    <!-- Section 6: Visual Artifacts -->
    {f'''
    <div class="infographic-container">
        <h1>6. Visual Investment Summary</h1>
        <h3>Investment Infographic</h3>
        <div class="artifact-container">
            <img src="data:image/{'jpeg' if infographic_path.suffix.lower() in ['.jpg', '.jpeg'] else 'png'};base64,{infographic_base64}" alt="Investment Infographic">
        </div>
        <div class="artifact-caption">AI-generated visual summary of key investment metrics</div>
    </div>
    ''' if infographic_base64 else '<div class="page-break"></div><h1>6. Visual Investment Summary</h1><p><em>Infographic generation in progress...</em></p>'}

    <!-- Section 7: Document Info -->
    <div class="page-break"></div>
    <h1>7. Document Information</h1>
    <div class="section-content">
        <p><strong>Generated:</strong> {current_date}</p>
        <p><strong>Analysis Pipeline:</strong> Multi-Agent AI Due Diligence System</p>
        <p><strong>Agents Deployed:</strong></p>
        <ul>
            <li>Company Research Agent (Web Intelligence)</li>
            <li>Market Analysis Agent (Competitive Intelligence)</li>
            <li>Financial Modeling Agent (Quantitative Analysis)</li>
            <li>Risk Assessment Agent (Risk Intelligence)</li>
            <li>Investor Memo Agent (Synthesis & Recommendation)</li>
        </ul>
        <p><strong>Data Sources:</strong> Real-time web search, public filings, news sources, industry reports</p>
        <p><strong>Classification:</strong> Highly Confidential - Internal Use Only</p>
    </div>

    <div style="margin-top: 50px; padding-top: 20px; border-top: 2px solid var(--border-color); text-align: center; font-size: 9pt; color: #666;">
        <p>This document was generated using AI-powered due diligence analysis.<br>
        All information should be independently verified before making investment decisions.</p>
        <p style="margin-top: 20px; color: #8b0000; font-weight: bold;">
            © {datetime.now().year} | Confidential & Proprietary | Do Not Distribute
        </p>
    </div>
</body>
</html>"""

        # Generate PDF from HTML
        pdf_bytes = HTML(string=html_content).write_pdf()

        # Save as ADK artifact
        artifact_name = f"comprehensive_report_{timestamp}.pdf"
        pdf_artifact = types.Part.from_bytes(
            data=pdf_bytes,
            mime_type="application/pdf"
        )

        version = await tool_context.save_artifact(filename=artifact_name, artifact=pdf_artifact)
        logger.info(f"Saved PDF artifact: {artifact_name} (version {version})")

        # Also save to outputs folder
        filepath = OUTPUTS_DIR / artifact_name
        filepath.write_bytes(pdf_bytes)

        result = {
            "status": "success",
            "message": f"Comprehensive PDF report saved as '{artifact_name}' - view in Artifacts tab",
            "artifact": artifact_name,
            "version": version,
            "includes": {
                "agent_outputs": ["company_info", "market_analysis", "financial_model", "risk_assessment", "investor_memo"],
                "artifacts": ["revenue_chart", "infographic"] if chart_base64 and infographic_base64 else [],
                "page_count": "~15-20 pages"
            }
        }

        # Send email if user_email is provided
        if user_email and user_email.strip():
            logger.info(f"Sending PDF report to user email: {user_email}")
            email_result = await send_email_with_pdf(
                recipient_email=user_email.strip(),
                pdf_bytes=pdf_bytes,
                pdf_filename=artifact_name,
                company_name=company_name
            )
            result["email"] = email_result

            if email_result["status"] == "success":
                result["message"] += f" | Report emailed to {user_email}"
            elif email_result["status"] == "error":
                result["message"] += f" | Email failed: {email_result['message']}"
            else:
                result["message"] += " | Email skipped (SMTP not configured)"

        return result

    except Exception as e:
        logger.error(f"Error generating PDF report: {e}")
        return {"status": "error", "message": str(e)}
