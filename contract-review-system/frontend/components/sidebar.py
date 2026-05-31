"""
侧边栏组件 - 系统信息、设置、Agent状态
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st


def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.header("📋 智能合同审查")

        st.markdown("---")

        # 系统信息
        st.subheader("ℹ️ 系统信息")
        st.markdown("""
        - **版本**: v1.0.0
        - **框架**: LangChain + LangGraph
        - **模型**: MIMO LLM
        """)

        st.markdown("---")

        # Agent状态
        st.subheader("🤖 Agent状态")
        agents = [
            ("📄 文档解析", "DocumentParserAgent"),
            ("📝 条款分析", "ClauseAnalysisAgent"),
            ("⚠️ 风险评估", "RiskAssessmentAgent"),
            ("✅ 合规检查", "ComplianceCheckerAgent"),
            ("📊 报告生成", "ReportGeneratorAgent"),
        ]

        for display_name, agent_name in agents:
            st.markdown(f"**{display_name}**")
            st.caption(agent_name)

        st.markdown("---")

        # 快速操作
        st.subheader("⚡ 快速操作")
        if st.button("🗑️ 清空对话历史", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["review_history"] = []
            st.rerun()

        if st.button("📥 下载示例合同", use_container_width=True):
            _show_sample_contract()

        st.markdown("---")

        # 帮助
        st.subheader("❓ 使用帮助")
        st.markdown("""
        1. 在对话框输入合同文本或上传文件
        2. 系统将自动进行多维度审查
        3. 查看审查报告和风险分析
        """)


def _show_sample_contract():
    """显示示例合同"""
    sample = """
技术服务合同

甲方：北京创新科技有限公司
乙方：上海智慧软件有限公司

第一条 合同标的
乙方为甲方提供企业级ERP系统的技术开发服务。

第二条 服务期限
合同有效期自2024年4月1日至2024年12月31日。

第三条 服务费用及支付
3.1 服务总费用为人民币壹佰伍拾万元整（¥1,500,000.00）。
3.2 甲方应在合同签订后5个工作日内支付30%预付款。

第四条 知识产权
4.1 本合同履行过程中产生的所有技术成果和知识产权归甲方所有。

第五条 保密条款
5.1 双方对本合同内容承担保密义务。

第六条 违约责任
6.1 如甲方违约，应承担无限责任。

第七条 争议解决
如发生争议，由乙方所在地法院管辖。
"""
    st.session_state["sample_contract"] = sample
    st.success("示例合同已加载，请在对话框中使用")
