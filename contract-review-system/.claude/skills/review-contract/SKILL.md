---
name: review-contract
description: >
  当用户要求【审查合同】【检查合同】【分析合同风险】时自动启用此skill。
  触发关键词：审查合同、合同审查、检查合同、合同风险、review contract
version: 0.1.0
argument-hint: "[合同文本或文件路径]"
---

# 合同审查Skill

审查合同文本，识别风险条款和合规问题。

## 审查维度

1. **违约责任** - 是否公平对等
2. **付款条款** - 付款条件是否合理
3. **知识产权** - 归属是否明确
4. **保密条款** - 范围和期限
5. **争议解决** - 管辖法院/仲裁
6. **单方解除权** - 是否对等

## 输出格式

```json
{
  "risk_level": "high|medium|low",
  "issues": [
    {
      "clause": "条款描述",
      "risk_type": "风险类型",
      "severity": "critical|high|medium|low",
      "suggestion": "修改建议"
    }
  ],
  "recommendations": ["建议1", "建议2"]
}
```

## 示例
```
/review-contract 合同文本内容...
```
