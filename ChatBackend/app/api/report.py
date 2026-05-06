from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from ..services.report_service import ReportService
import traceback
import uuid
import os
import json
import tempfile
import shutil
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont

# 创建报告API蓝图
report_api = Blueprint('report_api', __name__)

DEFAULT_PDF_RENDER_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    "/mnt/c/Windows/Fonts/msyh.ttc",
    "/mnt/c/Windows/Fonts/msyhbd.ttc",
    "/mnt/c/Windows/Fonts/simhei.ttf",
    "/mnt/c/Windows/Fonts/simsun.ttc",
    "/mnt/c/Windows/Fonts/simfang.ttf",
]


def _get_configured_font_candidates():
    configured = (os.getenv("WANXIANG_REPORT_FONT_PATHS") or os.getenv("ZHIMO_REPORT_FONT_PATHS") or "").strip()
    if configured:
        return [item.strip() for item in configured.split(",") if item.strip()]
    return list(DEFAULT_PDF_RENDER_FONT_CANDIDATES)

@report_api.route('/generate', methods=['POST'])
@login_required
def generate_report():
    """生成舆情分析报告"""
    try:
        # 获取请求数据
        data = request.get_json()
        if not data or 'sessionId' not in data:
            return jsonify({"success": False, "error": "缺少会话ID"}), 400

        session_id = data['sessionId']
        message = data.get('message')  # 可选：用户当前输入的消息内容

        current_app.logger.info(f"开始生成会话 {session_id} 的舆情报告")

        # 调用报告服务生成报告
        result, status_code = ReportService.generate_report(session_id, message=message)

        return jsonify(result), status_code
    except Exception as e:
        current_app.logger.error(f"生成报告时出错: {str(e)}")
        return jsonify({"success": False, "error": f"生成报告失败: {str(e)}"}), 500

@report_api.route('/export-pdf', methods=['POST'])
@login_required
def export_pdf():
    """将报告导出为PDF文件"""
    try:
        # 获取报告数据
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "缺少报告数据"}), 400

        report_data = data.get('reportData')
        report_id = data.get('report_id') or data.get('reportId')
        if not report_data and report_id:
            report_result, status_code = ReportService.get_report(report_id)
            if status_code != 200 or not report_result.get('success'):
                return jsonify(report_result), status_code
            report_data = report_result.get('data')

        if not report_data:
            return jsonify({"success": False, "error": "缺少报告数据"}), 400
        
        # 创建临时HTML文件
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as html_file:
            html_path = html_file.name
            
            # 使用报告数据生成HTML内容
            html_content = generate_html_report(report_data)
            html_file.write(html_content.encode('utf-8'))
        
        # 使用pdfkit生成PDF
        pdf_path = html_path.replace('.html', '.pdf')
        
        try:
            wkhtmltopdf_path = shutil.which('wkhtmltopdf')
            if not wkhtmltopdf_path:
                raise RuntimeError("未找到 wkhtmltopdf，改用 Pillow PDF 兜底")

            # 尝试使用pdfkit生成PDF
            import pdfkit
            try:
                pdfkit.from_file(
                    html_path,
                    pdf_path,
                    configuration=pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
                )
                
                if os.path.exists(pdf_path):
                    # 准备返回PDF文件
                    filename = f"report_{uuid.uuid4().hex[:8]}.pdf"
                    return send_file(
                        pdf_path,
                        as_attachment=True,
                        download_name=filename,
                        mimetype='application/pdf'
                    )
                else:
                    raise Exception("PDF生成失败")
            except Exception as pdf_err:
                current_app.logger.error(f"PDF生成失败，回退为 Pillow PDF 导出: {str(pdf_err)}")
                generate_pillow_pdf_report(report_data, pdf_path)
                filename = f"report_{uuid.uuid4().hex[:8]}.pdf"
                return send_file(
                    pdf_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/pdf'
                )
        except Exception as e:
            current_app.logger.error(f"导出失败，回退为 Pillow PDF 导出: {str(e)}")
            try:
                generate_pillow_pdf_report(report_data, pdf_path)
                filename = f"report_{uuid.uuid4().hex[:8]}.pdf"
                return send_file(
                    pdf_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/pdf'
                )
            except Exception as pillow_err:
                current_app.logger.error(f"Pillow PDF 导出失败，最终回退为HTML导出: {str(pillow_err)}")
                response = current_app.make_response(html_content)
                response.headers["Content-Type"] = "text/html"
                response.headers["Content-Disposition"] = f"attachment; filename=report_{uuid.uuid4().hex[:8]}.html"
                return response
                
    except Exception as e:
        current_app.logger.error(f"导出PDF时出错: {str(e)}")
        return jsonify({"success": False, "error": f"导出PDF失败: {str(e)}"}), 500
    finally:
        # 清理临时文件
        try:
            if 'html_path' in locals() and os.path.exists(html_path):
                os.remove(html_path)
            if 'pdf_path' in locals() and os.path.exists(pdf_path):
                os.remove(pdf_path)
        except:
            pass

def get_pdf_render_font_path():
    """Choose an available CJK-capable font for Pillow PDF rendering."""
    for candidate in _get_configured_font_candidates():
        if os.path.exists(candidate):
            return candidate
    current_app.logger.warning("未找到可用的中文字体文件，将回退到 Pillow 默认字体")
    return None

def wrap_text_for_font(draw, text, font, max_width):
    """Wrap text to fit the given width."""
    text = str(text or "")
    if not text:
        return [""]

    wrapped_lines = []
    for paragraph in text.splitlines():
        if not paragraph:
            wrapped_lines.append("")
            continue

        current = ""
        for char in paragraph:
            trial = current + char
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = trial
            else:
                wrapped_lines.append(current)
                current = char
        if current:
            wrapped_lines.append(current)

    return wrapped_lines


def ensure_dict(value):
    return value if isinstance(value, dict) else {}


def ensure_list(value):
    return value if isinstance(value, list) else []


def ensure_string_list(value):
    return [str(item) for item in ensure_list(value) if item is not None]


def normalize_named_items(items, text_key="name", default_prefix="条目"):
    normalized = []
    for index, item in enumerate(ensure_list(items), start=1):
        if isinstance(item, dict):
            normalized.append(item)
        elif item is not None:
            normalized.append({text_key: str(item), "value": max(1, len(ensure_list(items)) - index + 1)})
    return normalized


def normalize_object_list(items, fallback_key):
    normalized = []
    for item in ensure_list(items):
        if isinstance(item, dict):
            normalized.append(item)
        elif item is not None:
            normalized.append({fallback_key: str(item)})
    return normalized

def build_report_plain_text(report_data):
    """Build a readable plain-text version of the report for PDF fallback rendering."""
    meta = ensure_dict(report_data.get('meta'))
    executive = ensure_dict(report_data.get('executiveSummary'))
    insights = ensure_dict(report_data.get('insightsAndRecommendations'))
    recommendations = normalize_object_list(insights.get('recommendations'), 'description')
    challenges = normalize_object_list(insights.get('keyChallenges'), 'description')
    risk_assessment = ensure_dict(insights.get('riskAssessment'))
    risks = normalize_object_list(risk_assessment.get('potentialRisks'), 'mitigationStrategy')
    overall = ensure_dict(executive.get('overallSentiment'))
    distribution = ensure_dict(overall.get('distribution'))

    lines = [
        meta.get('title', '舆情分析报告'),
        meta.get('subtitle', ''),
        '',
        f"生成时间：{meta.get('generatedAt', '未知')}",
        f"报告版本：{meta.get('version', '未知')}",
        f"置信度：{meta.get('confidenceLevel', '未知')}",
        '',
        '一、关键发现',
    ]

    for item in ensure_string_list(executive.get('keyFindings'))[:8]:
        lines.append(f"- {item}")

    lines.extend([
        '',
        '二、总体判断',
        f"情绪标签：{overall.get('label', '未知')}",
        f"情绪分数：{overall.get('score', '未知')}",
        f"情绪分布：正面 {distribution.get('positive', '未知')} / 中性 {distribution.get('neutral', '未知')} / 负面 {distribution.get('negative', '未知')}",
        f"热度等级：{executive.get('heatLevel', '未知')}",
        f"影响等级：{executive.get('impactLevel', '未知')}",
        '',
        '三、建议动作',
    ])

    for idx, item in enumerate(recommendations[:10], start=1):
        lines.append(f"{idx}. {item.get('title') or item.get('description') or item.get('recommendation') or '未命名建议'}")
        lines.append(f"   优先级：{item.get('priority', '未知')}")
        lines.append(f"   时段：{item.get('timeframe', '未知')}")
        lines.append(f"   内容：{item.get('description', '')}")
        if item.get('expectedOutcome'):
            lines.append(f"   预期：{item.get('expectedOutcome')}")

    if challenges:
        lines.extend(['', '四、关键挑战'])
        for item in challenges[:8]:
            challenge_name = item.get('challenge') or item.get('title') or item.get('description') or '未命名挑战'
            lines.append(f"- {challenge_name}：{item.get('description', '')}")

    if risks:
        lines.extend(['', '五、潜在风险'])
        for item in risks[:8]:
            lines.append(
                f"- {item.get('risk', '未命名风险')}：概率 {item.get('probability', '未知')}，影响 {item.get('impact', '未知')}，缓解 {item.get('mitigationStrategy', '')}"
            )

    lines.extend([
        '',
        '六、完整数据（JSON 摘录）',
        json.dumps(report_data, ensure_ascii=False, indent=2),
    ])

    return "\n".join(lines)

def generate_pillow_pdf_report(report_data, pdf_path):
    """Render a simple multi-page PDF using Pillow without external PDF tools."""
    font_path = get_pdf_render_font_path()
    if font_path:
        title_font = ImageFont.truetype(font_path, 42)
        body_font = ImageFont.truetype(font_path, 26)
    else:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    page_width = 1654
    page_height = 2339
    margin_x = 120
    margin_y = 120
    line_gap = 14
    usable_width = page_width - margin_x * 2

    probe = Image.new("RGB", (page_width, page_height), "white")
    probe_draw = ImageDraw.Draw(probe)
    raw_text = build_report_plain_text(report_data)

    lines = []
    for index, paragraph in enumerate(raw_text.splitlines()):
        font = title_font if index == 0 else body_font
        wrapped = wrap_text_for_font(probe_draw, paragraph, font, usable_width)
        if not wrapped:
            wrapped = [""]
        for line in wrapped:
            lines.append((line, font))

    pages = []
    image = Image.new("RGB", (page_width, page_height), "white")
    draw = ImageDraw.Draw(image)
    y = margin_y

    for line, font in lines:
        bbox = draw.textbbox((0, 0), line or " ", font=font)
        line_height = (bbox[3] - bbox[1]) + line_gap
        if y + line_height > page_height - margin_y:
            pages.append(image)
            image = Image.new("RGB", (page_width, page_height), "white")
            draw = ImageDraw.Draw(image)
            y = margin_y

        draw.text((margin_x, y), line, fill="black", font=font)
        y += line_height

    pages.append(image)
    first_page, *rest_pages = pages
    first_page.save(pdf_path, "PDF", resolution=150.0, save_all=True, append_images=rest_pages)

def generate_html_report(report_data):
    """根据报告数据生成HTML内容"""
    try:
        meta = ensure_dict(report_data.get('meta'))
        title = meta.get('title', '舆情分析报告')
        
        # 构建HTML内容 - 优化样式和布局
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                /* 基础样式优化 */
                body {{
                    font-family: "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    color: #333;
                    line-height: 1.5;
                    background-color: #f5f5f5;
                }}
                .report-container {{
                    max-width: 900px;
                    margin: 0 auto;
                    background: white;
                    padding: 40px;
                    box-shadow: 0 0 15px rgba(0,0,0,0.1);
                    border-top: 4px solid #1677ff;
                }}
                .report-title {{
                    font-size: 28px;
                    font-weight: bold;
                    text-align: center;
                    margin-bottom: 25px;
                    color: #1677ff;
                    padding-bottom: 15px;
                    border-bottom: 2px solid #f0f0f0;
                }}
                .report-subtitle {{
                    font-size: 18px;
                    text-align: center;
                    margin-bottom: 20px;
                    color: #666;
                }}
                .report-header {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 30px;
                    border-bottom: 1px solid #f0f0f0;
                    padding-bottom: 20px;
                }}
                .report-header p {{
                    margin: 8px 0;
                    color: #595959;
                }}
                .report-section {{
                    margin-bottom: 35px;
                    padding-bottom: 20px;
                    border-bottom: 1px solid #f0f0f0;
                }}
                .section-title {{
                    font-size: 22px;
                    font-weight: bold;
                    margin-bottom: 20px;
                    color: #1677ff;
                    padding-bottom: 10px;
                    border-bottom: 1px dashed #e8e8e8;
                }}
                .subsection-title {{
                    font-size: 18px;
                    font-weight: bold;
                    margin: 20px 0 15px 0;
                    color: #333;
                }}
                ul, ol {{
                    margin-left: 20px;
                    margin-bottom: 20px;
                    padding-left: 15px;
                }}
                li {{
                    margin-bottom: 8px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                table, th, td {{
                    border: 1px solid #e8e8e8;
                }}
                th {{
                    background-color: #f5f5f5;
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                }}
                td {{
                    padding: 12px;
                    text-align: left;
                }}
                tr:nth-child(even) {{
                    background-color: #fbfbfb;
                }}
                /* 数据展示卡片 */
                .stat-container {{
                    display: flex;
                    justify-content: space-around;
                    flex-wrap: wrap;
                    margin: 25px 0;
                }}
                .stat-item {{
                    text-align: center;
                    padding: 20px;
                    background: #f9f9f9;
                    border-radius: 8px;
                    width: 28%;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                }}
                .stat-value {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #1677ff;
                    margin-bottom: 8px;
                }}
                .stat-label {{
                    font-size: 14px;
                    color: #888;
                }}
                /* 情感分析展示 */
                .sentiment-bar {{
                    display: flex;
                    height: 40px;
                    width: 100%;
                    margin: 15px 0;
                    border-radius: 4px;
                    overflow: hidden;
                }}
                .sentiment-positive {{
                    background-color: #52c41a;
                    color: white;
                    text-align: center;
                    padding: 10px 0;
                }}
                .sentiment-neutral {{
                    background-color: #1677ff;
                    color: white;
                    text-align: center;
                    padding: 10px 0;
                }}
                .sentiment-negative {{
                    background-color: #f5222d;
                    color: white;
                    text-align: center;
                    padding: 10px 0;
                }}
                /* 数据图表替代样式 */
                .chart-container {{
                    background: #fff;
                    border: 1px solid #f0f0f0;
                    border-radius: 8px;
                    padding: 25px;
                    margin: 20px 0;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
                }}
                .chart-title {{
                    font-size: 16px;
                    font-weight: bold;
                    margin-bottom: 15px;
                    color: #333;
                }}
                .data-table {{
                    width: 100%;
                }}
                .data-bar {{
                    display: flex;
                    height: 30px;
                    margin: 8px 0;
                }}
                .data-bar-label {{
                    width: 30%;
                    font-weight: bold;
                    padding-right: 15px;
                    text-align: right;
                    line-height: 30px;
                }}
                .data-bar-value {{
                    flex-grow: 1;
                }}
                .data-bar-inner {{
                    background-color: #1677ff;
                    height: 100%;
                    color: white;
                    text-align: right;
                    padding-right: 10px;
                    line-height: 30px;
                    border-radius: 4px;
                }}
                /* 风险级别样式 */
                .risk-high {{
                    color: #f5222d;
                    font-weight: bold;
                }}
                .risk-medium {{
                    color: #fa8c16;
                    font-weight: bold;
                }}
                .risk-low {{
                    color: #52c41a;
                    font-weight: bold;
                }}
                .challenge-card {{
                    background-color: #fff7f7;
                    border: 1px solid #ffccc7;
                    border-radius: 6px;
                    padding: 15px;
                    margin-bottom: 15px;
                }}
                .opportunity-card {{
                    background-color: #f6ffed;
                    border: 1px solid #b7eb8f;
                    border-radius: 6px;
                    padding: 15px;
                    margin-bottom: 15px;
                }}
                .recommendation-card {{
                    background-color: #e6f7ff;
                    border: 1px solid #91d5ff;
                    border-radius: 6px;
                    padding: 15px;
                    margin-bottom: 15px;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 40px;
                    padding-top: 20px;
                    font-size: 12px;
                    color: #999;
                    border-top: 1px solid #f0f0f0;
                }}
            </style>
        </head>
        <body>
            <div class="report-container">
                <div class="report-title">{title}</div>
        """
        
        # 添加副标题（如果有）
        if meta.get('subtitle'):
            html += f"""
                <div class="report-subtitle">{meta.get('subtitle')}</div>
            """
        
        # 添加元数据
        html += f"""
                <div class="report-header">
                    <div>
                        <p><strong>生成时间:</strong> {meta.get('generatedAt', '').replace('T', ' ').split('.')[0]}</p>
                        <p><strong>报告ID:</strong> {meta.get('reportId', '')}</p>
                        <p><strong>版本:</strong> {meta.get('version', '1.0')}</p>
                    </div>
                    <div>
                        <p><strong>可信度:</strong> {int(meta.get('confidenceLevel', 0.8) * 100)}%</p>
                        <p><strong>关键词:</strong> {', '.join(meta.get('keywords', []))}</p>
                        <p><strong>分析上下文:</strong> {meta.get('analysisContext', '')}</p>
                    </div>
                </div>
        """
        
        # 添加执行摘要
        exec_summary = ensure_dict(report_data.get('executiveSummary'))
        html += f"""
                <div class="report-section">
                    <div class="section-title">执行摘要</div>
                    
                    <div class="subsection-title">关键发现</div>
                    <ul>
        """
        
        for finding in ensure_string_list(exec_summary.get('keyFindings')):
            html += f"<li>{finding}</li>\n"
            
        sentiment = ensure_dict(exec_summary.get('overallSentiment'))
        sentiment_dist = ensure_dict(sentiment.get('distribution'))
        
        # 改进情感分布视觉呈现
        pos_percent = sentiment_dist.get('positive', 0)
        neg_percent = sentiment_dist.get('negative', 0)
        neu_percent = sentiment_dist.get('neutral', 0)
        
        html += f"""
                    </ul>
                    
                    <div class="subsection-title">整体情感倾向</div>
                    <p><strong>{sentiment.get('label', '中性')}</strong> 
                       (得分: {int(sentiment.get('score', 0.5) * 100)}%)</p>
                    
                    <div class="sentiment-bar">
                        <div class="sentiment-positive" style="width: {pos_percent}%;">{pos_percent}%</div>
                        <div class="sentiment-neutral" style="width: {neu_percent}%;">{neu_percent}%</div>
                        <div class="sentiment-negative" style="width: {neg_percent}%;">{neg_percent}%</div>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                        <div>正面情感</div>
                        <div>中性情感</div>
                        <div>负面情感</div>
                    </div>
                    
                    <div class="stat-container">
                        <div class="stat-item">
                            <div class="stat-value">{exec_summary.get('heatLevel', 0)}</div>
                            <div class="stat-label">舆情热度</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{exec_summary.get('impactLevel', 0)}</div>
                            <div class="stat-label">影响力等级</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{len(exec_summary.get('topTrends', []))}</div>
                            <div class="stat-label">热门趋势</div>
                        </div>
                    </div>
                    
                    <!-- 热门趋势数据展示 -->
                    <div class="chart-container">
                        <div class="chart-title">热门趋势</div>
        """
        
        # 添加热门趋势的数据条形图替代
        trends = normalize_named_items(exec_summary.get('topTrends'), text_key="name", default_prefix="趋势")
        if trends:
            # 找出趋势值的最大值，用于计算百分比宽度
            max_trend_value = max([trend.get('value', 0) for trend in trends])
            
            for trend in trends:
                name = trend.get('name', '')
                value = trend.get('value', 0)
                sentiment = trend.get('sentiment', '中性')
                
                # 根据情感选择颜色
                color = "#1677ff"  # 默认中性蓝色
                if sentiment == '正面':
                    color = "#52c41a"  # 绿色
                elif sentiment == '负面':
                    color = "#f5222d"  # 红色
                
                # 计算百分比宽度
                width_percent = (value / max_trend_value) * 100 if max_trend_value > 0 else 0
                
                html += f"""
                        <div class="data-bar">
                            <div class="data-bar-label">{name}</div>
                            <div class="data-bar-value">
                                <div class="data-bar-inner" style="width: {width_percent}%; background-color: {color};">
                                    {value}
                                </div>
                            </div>
                        </div>
                """
        
        html += """
                    </div>
                </div>
        """
        
        # 添加详细分析
        detailed = ensure_dict(report_data.get('detailedAnalysis'))
        sentiment_analysis = ensure_dict(detailed.get('sentimentAnalysis'))
        
        html += f"""
                <div class="report-section">
                    <div class="section-title">详细分析</div>
                    
                    <div class="subsection-title">情感分析</div>
                    <p>{sentiment_analysis.get('overview', '')}</p>
                    
                    <!-- 情感维度分析 -->
                    <div class="chart-container">
                        <div class="chart-title">情感维度分析</div>
        """
        
        # 添加情感维度的数据条形图替代
        sentiment_details = normalize_object_list(sentiment_analysis.get('details'), 'dimension')
        if sentiment_details:
            # 找出得分的最大值，用于计算百分比宽度
            max_score = max([detail.get('score', 0) for detail in sentiment_details])
            
            for detail in sentiment_details:
                dimension = detail.get('dimension', '')
                score = detail.get('score', 0)
                description = detail.get('description', '')
                
                # 计算百分比宽度
                width_percent = (score / max_score) * 100 if max_score > 0 else 0
                
                html += f"""
                        <div class="data-bar">
                            <div class="data-bar-label">{dimension}</div>
                            <div class="data-bar-value">
                                <div class="data-bar-inner" style="width: {width_percent}%;">
                                    {score}
                                </div>
                            </div>
                        </div>
                        <div style="margin-left: 30%; margin-bottom: 15px; color: #666; font-size: 14px;">
                            {description}
                        </div>
                """
        
        html += """
                    </div>
        """
            
        # 添加情感因素分析
        emotional_factors = normalize_object_list(sentiment_analysis.get('emotionalFactors'), 'factor')
        if emotional_factors:
            html += """
                    <div class="chart-container">
                        <div class="chart-title">情感影响因素</div>
            """
            
            # 找出影响值的最大绝对值，用于计算百分比宽度
            max_impact = max([abs(factor.get('impact', 0)) for factor in emotional_factors])
            
            for factor in emotional_factors:
                factor_name = factor.get('factor', '')
                impact = factor.get('impact', 0)
                description = factor.get('description', '')
                
                # 计算百分比宽度并根据正负值选择颜色
                width_percent = (abs(impact) / max_impact) * 100 if max_impact > 0 else 0
                color = "#52c41a" if impact > 0 else "#f5222d"
                
                html += f"""
                        <div class="data-bar">
                            <div class="data-bar-label">{factor_name}</div>
                            <div class="data-bar-value">
                                <div class="data-bar-inner" style="width: {width_percent}%; background-color: {color};">
                                    {impact}
                                </div>
                            </div>
                        </div>
                        <div style="margin-left: 30%; margin-bottom: 15px; color: #666; font-size: 14px;">
                            {description}
                        </div>
                """
            
            html += """
                    </div>
            """
        
        # 添加话题分析
        topic_analysis = ensure_dict(detailed.get('topicAnalysis'))
        html += f"""
                    <div class="subsection-title">话题分析</div>
                    <p>{topic_analysis.get('overview', '')}</p>
                    
                    <!-- 主要话题分析 -->
                    <div class="chart-container">
                        <div class="chart-title">主要话题分析</div>
                        <table>
                            <tr>
                                <th>话题</th>
                                <th>权重</th>
                                <th>情感倾向</th>
                                <th>来源数量</th>
                                <th>相关关键词</th>
                            </tr>
        """
        
        for topic in normalize_object_list(topic_analysis.get('mainTopics'), 'topic'):
            # 根据情感选择样式类
            sentiment_class = ""
            if topic.get('sentiment') == '正面':
                sentiment_class = "risk-low"
            elif topic.get('sentiment') == '负面':
                sentiment_class = "risk-high"
            
            html += f"""
                            <tr>
                                <td><strong>{topic.get('topic', '')}</strong></td>
                                <td>{topic.get('weight', 0)}</td>
                                <td class="{sentiment_class}">{topic.get('sentiment', '中性')}</td>
                                <td>{topic.get('sourceCount', 0)}</td>
                                <td>{', '.join(topic.get('relatedKeywords', []))}</td>
                            </tr>
            """
            
        html += """
                        </table>
                    </div>
                </div>
        """
        
        # 添加传播分析
        propagation_analysis = ensure_dict(detailed.get('propagationAnalysis'))
        html += f"""
                <div class="report-section">
                    <div class="section-title">传播分析</div>
                    <p>{propagation_analysis.get('overview', '')}</p>
                    
                    <!-- 传播渠道分析 -->
                    <div class="chart-container">
                        <div class="chart-title">传播渠道分析</div>
                        <table>
                            <tr>
                                <th>渠道</th>
                                <th>数量</th>
                                <th>影响力</th>
                                <th>情感分布</th>
                            </tr>
        """
        
        for channel in normalize_object_list(propagation_analysis.get('channels'), 'name'):
            sentiment_data = ensure_dict(channel.get('sentiment'))
            sentiment_str = f"正面: {sentiment_data.get('positive', 0)}%, 负面: {sentiment_data.get('negative', 0)}%, 中性: {sentiment_data.get('neutral', 0)}%"
            
            html += f"""
                            <tr>
                                <td><strong>{channel.get('name', '')}</strong></td>
                                <td>{channel.get('volume', 0)}</td>
                                <td>{channel.get('influence', 0)}/10</td>
                                <td>{sentiment_str}</td>
                            </tr>
            """
            
        html += """
                        </table>
                    </div>
                    
                    <!-- 传播高峰事件 -->
                    <div class="chart-container">
                        <div class="chart-title">传播高峰事件</div>
        """
        
        for event in normalize_object_list(propagation_analysis.get('peakEvents'), 'title'):
            timestamp = event.get('timestamp', '').replace('T', ' ').split('.')[0]
            
            html += f"""
                        <div style="margin-bottom: 15px; padding: 15px; border: 1px solid #f0f0f0; border-radius: 6px;">
                            <div style="font-weight: bold;">{event.get('title', '')}</div>
                            <div>时间: {timestamp}</div>
                            <div>影响度: {event.get('impact', 0)}/10</div>
                            <div style="margin-top: 8px;">{event.get('description', '')}</div>
                        </div>
            """
            
        html += """
                    </div>
                </div>
        """
        
        # 添加受众分析
        audience_analysis = ensure_dict(detailed.get('audienceAnalysis'))
        if audience_analysis:
            html += f"""
                <div class="report-section">
                    <div class="section-title">受众分析</div>
                    <p>{audience_analysis.get('overview', '')}</p>
                    
                    <!-- 人口统计学分析 -->
                    <div class="chart-container">
                        <div class="chart-title">人口统计学特征</div>
            """
            
            for demographic in normalize_object_list(audience_analysis.get('demographics'), 'type'):
                demo_type = demographic.get('type', '')
                
                html += f"""
                        <div style="margin-bottom: 20px;">
                            <h4 style="margin-bottom: 10px;">{demo_type}</h4>
                """
                
                # 找出最大百分比，用于计算宽度
                groups = normalize_object_list(demographic.get('groups'), 'name')
                max_percentage = max([group.get('percentage', 0) for group in groups], default=0)
                
                for group in groups:
                    name = group.get('name', '')
                    percentage = group.get('percentage', 0)
                    width_percent = (percentage / max_percentage) * 100 if max_percentage > 0 else 0
                    
                    html += f"""
                            <div class="data-bar">
                                <div class="data-bar-label">{name}</div>
                                <div class="data-bar-value">
                                    <div class="data-bar-inner" style="width: {width_percent}%;">
                                        {percentage}%
                                    </div>
                                </div>
                            </div>
                    """
                
                html += """
                        </div>
                """
            
            html += """
                    </div>
                </div>
            """
        
        # 添加洞察与建议
        insights = ensure_dict(report_data.get('insightsAndRecommendations'))
        html += f"""
                <div class="report-section">
                    <div class="section-title">洞察与建议</div>
                    
                    <div class="subsection-title">关键挑战</div>
        """
        
        for challenge in normalize_object_list(insights.get('keyChallenges'), 'challenge'):
            challenge_title = challenge.get('challenge') or challenge.get('title') or challenge.get('description', '')
            html += f"""
                    <div class="challenge-card">
                        <div style="font-weight: bold; margin-bottom: 8px;">{challenge_title}</div>
                        <div>严重度: <strong>{challenge.get('severity', 0)}/10</strong></div>
                        <div style="margin-top: 8px;">{challenge.get('description', '')}</div>
                    </div>
            """
        
        html += """
                    <div class="subsection-title">机会点</div>
        """
        
        for opportunity in normalize_object_list(insights.get('opportunities'), 'opportunity'):
            opportunity_title = opportunity.get('opportunity') or opportunity.get('title') or opportunity.get('description', '')
            html += f"""
                    <div class="opportunity-card">
                        <div style="font-weight: bold; margin-bottom: 8px;">{opportunity_title}</div>
                        <div>潜力: <strong>{opportunity.get('potential', 0)}/10</strong></div>
                        <div style="margin-top: 8px;">{opportunity.get('description', '')}</div>
                    </div>
            """
            
        html += """
                    <div class="subsection-title">建议</div>
        """
        
        for recommendation in normalize_object_list(insights.get('recommendations'), 'description'):
            # 根据优先级选择样式
            priority_class = ""
            if recommendation.get('priority') == '高':
                priority_class = "risk-high"
            elif recommendation.get('priority') == '中':
                priority_class = "risk-medium"
            else:
                priority_class = "risk-low"

            recommendation_title = (
                recommendation.get('title')
                or recommendation.get('recommendation')
                or recommendation.get('description', '')
            )
            
            html += f"""
                    <div class="recommendation-card">
                        <div style="font-weight: bold; margin-bottom: 8px;">{recommendation_title}</div>
                        <div>
                            优先级: <span class="{priority_class}">{recommendation.get('priority', '中')}</span>
                            | 时间框架: {recommendation.get('timeframe', '')}
                        </div>
                        <div style="margin-top: 8px;">{recommendation.get('description', '')}</div>
                        <div style="margin-top: 8px; font-style: italic;">预期效果: {recommendation.get('expectedOutcome', '')}</div>
                    </div>
            """
            
        # 添加风险评估
        risk_assessment = ensure_dict(insights.get('riskAssessment'))
        risk_level = risk_assessment.get('riskLevel', '中')
        risk_class = "risk-medium"
        if risk_level == '高':
            risk_class = "risk-high"
        elif risk_level == '低':
            risk_class = "risk-low"
            
        html += f"""
                    <div class="subsection-title">风险评估</div>
                    <div style="padding: 15px; background-color: #fffbe6; border: 1px solid #ffe58f; border-radius: 6px; margin-bottom: 20px;">
                        <div>总体风险等级: <span class="{risk_class}">{risk_level}</span></div>
                        
                        <div style="margin-top: 15px;"><strong>潜在风险</strong></div>
        """
        
        for risk in normalize_object_list(risk_assessment.get('potentialRisks'), 'risk'):
            # 计算风险热力值 (概率 x 影响)
            risk_heat = (risk.get('probability', 0) * risk.get('impact', 0)) / 100
            risk_heat_class = "risk-medium"
            if risk_heat > 60:
                risk_heat_class = "risk-high"
            elif risk_heat < 30:
                risk_heat_class = "risk-low"
                
            html += f"""
                        <div style="margin: 10px 0; padding: 10px; background-color: white; border-radius: 4px; border: 1px solid #f0f0f0;">
                            <div style="font-weight: bold; margin-bottom: 5px;">{risk.get('risk', '')}</div>
                            <div>风险热度: <span class="{risk_heat_class}">{risk_heat:.1f}</span> (概率: {risk.get('probability', 0)}% × 影响: {risk.get('impact', 0)}%)</div>
                            <div style="margin-top: 8px;"><strong>缓解策略:</strong> {risk.get('mitigationStrategy', '')}</div>
                        </div>
            """
        
        html += """
                    </div>
                </div>
        """
        
        # 添加分析方法与数据来源
        analysis_details = ensure_dict(report_data.get('analysisDetails'))
        
        html += """
                <div class="report-section">
                    <div class="section-title">分析方法与数据来源</div>
                    
                    <div class="subsection-title">分析方法</div>
                    <ul>
        """
        
        for methodology in ensure_string_list(analysis_details.get('methodologies')):
            html += f"<li>{methodology}</li>\n"
            
        html += """
                    </ul>
                    
                    <div class="subsection-title">数据来源</div>
                    <table>
                        <tr>
                            <th>来源名称</th>
                            <th>类型</th>
                            <th>可靠性</th>
                            <th>覆盖率</th>
                        </tr>
        """
        
        for source in normalize_object_list(analysis_details.get('dataSources'), 'name'):
            html += f"""
                        <tr>
                            <td>{source.get('name') or source.get('source', '')}</td>
                            <td>{source.get('type', '')}</td>
                            <td>{source.get('reliability', 0)}%</td>
                            <td>{source.get('coverage', 0)}%</td>
                        </tr>
            """
            
        html += """
                    </table>
                    
                    <div class="subsection-title">分析局限性</div>
                    <ul>
        """
        
        for limitation in ensure_string_list(analysis_details.get('limitations')):
            html += f"<li>{limitation}</li>\n"
            
        html += """
                    </ul>
                </div>
        """
        
        # 添加原始数据摘要
        raw_data = ensure_dict(report_data.get('rawDataSummary'))
        
        html += f"""
                <div class="report-section">
                    <div class="section-title">数据摘要</div>
                    
                    <div class="stat-container">
                        <div class="stat-item">
                            <div class="stat-value">{raw_data.get('totalSources', 0)}</div>
                            <div class="stat-label">数据来源总数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{raw_data.get('totalMessages', 0)}</div>
                            <div class="stat-label">消息总数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{len(ensure_list(raw_data.get('sampleData')))}</div>
                            <div class="stat-label">样本数量</div>
                        </div>
                    </div>
                    
                    <div class="subsection-title">样本数据</div>
                    <table>
                        <tr>
                            <th>内容</th>
                            <th>来源</th>
                            <th>时间</th>
                            <th>情感</th>
                        </tr>
        """
        
        for sample in normalize_object_list(raw_data.get('sampleData'), 'content')[:5]:  # 只显示前5条样本
            timestamp = sample.get('timestamp', '').replace('T', ' ').split('.')[0]
            
            # 根据情感选择样式
            sentiment_class = ""
            if sample.get('sentiment') == '正面':
                sentiment_class = "risk-low"
            elif sample.get('sentiment') == '负面':
                sentiment_class = "risk-high"
                
            html += f"""
                        <tr>
                            <td>{sample.get('content', '')}</td>
                            <td>{sample.get('source', '')}</td>
                            <td>{timestamp}</td>
                            <td class="{sentiment_class}">{sample.get('sentiment', '中性')}</td>
                        </tr>
            """
            
        html += """
                    </table>
                </div>
        """
        
        # 添加页脚
        html += f"""
                <div class="footer">
                    <p>©{meta.get('generatedAt', '').split('T')[0].split('-')[0]} 基于微调Deepseek的舆情策略生成系统</p>
                    <p>报告生成时间: {meta.get('generatedAt', '').replace('T', ' ').split('.')[0]}</p>
                    <p>关键词: {', '.join(meta.get('keywords', []))}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        current_app.logger.error(f"生成HTML报告失败: {str(e)}")
        # 返回一个最小的错误页面
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>报告生成失败</title>
        </head>
        <body>
            <h1>报告生成失败</h1>
            <p>错误信息: {str(e)}</p>
        </body>
        </html>
        """

@report_api.route('/<report_id>', methods=['GET'])
@login_required
def get_report(report_id):
    """获取特定报告"""
    try:
        if not report_id:
            return jsonify({"success": False, "error": "缺少报告ID参数"}), 400

        current_app.logger.info(f"获取报告 {report_id}")

        # 调用报告服务获取报告
        result, status_code = ReportService.get_report(report_id)
        
        return jsonify(result), status_code
        
    except Exception as e:
        current_app.logger.error(f"获取报告时发生错误: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"处理请求失败: {str(e)}"
        }), 500
