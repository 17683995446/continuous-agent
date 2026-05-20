#!/usr/bin/env python3
"""
代码执行器
=========
负责实际执行代码工程任务
"""

import os
import re
import json
import subprocess
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import time
import hashlib

logger = logging.getLogger("CodeExecutor")


@dataclass
class CodeContext:
    """代码上下文"""
    file_path: Optional[str] = None
    code_content: Optional[str] = None
    language: Optional[str] = None
    project_root: Optional[str] = None
    related_files: List[str] = field(default_factory=list)


class CodeExecutor:
    """
    代码执行器
    
    功能：
    - 代码分析和理解
    - 代码修改和生成
    - 测试执行
    - 错误诊断和修复
    """
    
    SUPPORTED_LANGUAGES = {
        'python': ['.py'],
        'javascript': ['.js', '.jsx', '.mjs'],
        'typescript': ['.ts', '.tsx'],
        'java': ['.java'],
        'go': ['.go'],
        'rust': ['.rs'],
        'cpp': ['.cpp', '.cc', '.cxx', '.c'],
        'c': ['.c'],
        'ruby': ['.rb'],
        'php': ['.php'],
    }
    
    def __init__(self, workspace: str = "/data/user/work"):
        self.workspace = Path(workspace)
        self.execution_history: List[Dict[str, Any]] = []
        
    def execute(
        self,
        task: Any,
        experience: List[Dict[str, Any]],
        workspace: str
    ) -> Any:
        """
        执行任务
        
        Args:
            task: 任务对象
            experience: 相关经验
            workspace: 工作目录
            
        Returns:
            执行结果
        """
        from ..core.engine import TaskResult, TaskType
        
        self.workspace = Path(workspace)
        task_type = task.task_type
        
        try:
            logger.info(f"执行任务 [{task.id}] 类型={task_type.value} 描述={task.description[:50]}")
            if task_type == TaskType.ANALYZE:
                result = self._analyze(task, experience)
            elif task_type == TaskType.FIX_BUG:
                result = self._fix_bug(task, experience)
            elif task_type == TaskType.IMPLEMENT:
                result = self._implement(task, experience)
            elif task_type == TaskType.REFACTOR:
                result = self._refactor(task, experience)
            elif task_type == TaskType.ADD_FEATURE:
                result = self._add_feature(task, experience)
            elif task_type == TaskType.OPTIMIZE:
                result = self._optimize(task, experience)
            elif task_type == TaskType.TEST:
                result = self._test(task, experience)
            elif task_type == TaskType.DOCUMENT:
                result = self._document(task, experience)
            else:
                logger.warning(f"未知的任务类型: {task_type}，任务ID: {task.id}")
                result = TaskResult(
                    success=False,
                    error=f"未知的任务类型: {task_type}"
                )
            
            # 记录执行历史（限制大小防止内存泄漏）
            self.execution_history.append({
                "task_id": task.id,
                "task_type": task_type.value,
                "success": result.success,
                "timestamp": time.time()
            })
            if len(self.execution_history) > 5000:
                self.execution_history = self.execution_history[-3000:]
            
            return result
            
        except Exception as e:
            logger.error(f"执行任务异常 [{task.id}] 类型={task_type.value}: {e}\n{traceback.format_exc()}")
            return TaskResult(
                success=False,
                error=str(e)
            )
    
    def _analyze(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """分析代码"""
        from ..core.engine import TaskResult
        
        context = task.context
        file_path = context.get('file_path')
        code_content = context.get('code_content')
        
        issues = []
        suggestions = []
        metrics = {}
        
        # 如果提供了文件路径，读取文件
        if file_path:
            file_path = Path(file_path)
            if file_path.exists():
                code_content = file_path.read_text(encoding='utf-8')
                language = self._detect_language(file_path.suffix)
            else:
                logger.warning(f"分析失败，文件不存在: {file_path}")
                return TaskResult(
                    success=False,
                    error=f"文件不存在: {file_path}"
                )
        elif code_content:
            language = context.get('language', 'python')
        else:
            return TaskResult(
                success=False,
                error="需要提供 file_path 或 code_content"
            )
        
        # 基于经验的优化建议
        for exp in experience:
            if exp.get('task_type') == 'analyze':
                suggestions.append(exp.get('experience', ''))
        
        # 执行分析
        if language == 'python':
            issues, metrics = self._analyze_python(code_content)
        elif language in ['javascript', 'typescript']:
            issues, metrics = self._analyze_js(code_content)
        else:
            issues = [{"type": "info", "message": f"语言 {language} 的分析功能待完善"}]
        
        return TaskResult(
            success=True,
            output={
                "issues": issues,
                "suggestions": suggestions,
                "metrics": metrics,
                "language": language
            },
            learnings=[f"分析完成，发现 {len(issues)} 个问题"]
        )
    
    def _analyze_python(self, code: str) -> Tuple[List[Dict], Dict]:
        """分析Python代码"""
        issues = []
        metrics = {
            "lines": len(code.split('\n')),
            "characters": len(code),
            "functions": 0,
            "classes": 0
        }
        
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 检查长行
            if len(line) > 120:
                issues.append({
                    "type": "style",
                    "line": i,
                    "message": f"行过长 ({len(line)} 字符)"
                })
            
            # 检查TODO/FIXME
            if 'TODO' in line or 'FIXME' in line:
                issues.append({
                    "type": "todo",
                    "line": i,
                    "message": line.strip()
                })
        
        # 统计函数和类
        metrics["functions"] = len(re.findall(r'^\s*def\s+\w+', code, re.MULTILINE))
        metrics["classes"] = len(re.findall(r'^\s*class\s+\w+', code, re.MULTILINE))
        
        # 检查复杂度
        if metrics["lines"] > 500:
            issues.append({
                "type": "complexity",
                "message": "文件较大，建议拆分"
            })
        
        return issues, metrics
    
    def _analyze_js(self, code: str) -> Tuple[List[Dict], Dict]:
        """分析JavaScript/TypeScript代码"""
        issues = []
        metrics = {
            "lines": len(code.split('\n')),
            "characters": len(code),
            "functions": 0,
            "classes": 0
        }
        
        # 统计函数
        metrics["functions"] = len(re.findall(r'function\s+\w+|=>\s*{|\w+\s*\([^)]*\)\s*{', code))
        metrics["classes"] = len(re.findall(r'class\s+\w+', code))
        
        return issues, metrics
    
    def _fix_bug(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """修复bug"""
        from ..core.engine import TaskResult
        
        context = task.context
        file_path = context.get('file_path')
        error_message = context.get('error_message', '')
        code_content = context.get('code_content')
        
        files_modified = []
        fix_description = ""
        
        if file_path:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"修复bug失败，文件不存在: {file_path}")
                return TaskResult(
                    success=False,
                    error=f"文件不存在: {file_path}"
                )
            code_content = file_path.read_text(encoding='utf-8')
        
        # 如果既没有文件路径也没有代码内容，无法修复
        if not code_content:
            logger.warning(f"修复bug失败，缺少代码内容")
            return TaskResult(
                success=False,
                error="需要提供 file_path 或 code_content 才能修复bug",
                learnings=["修复失败: 缺少代码内容"]
            )
        
        # 分析错误信息
        error_analysis = self._analyze_error(error_message, code_content)
        
        # 应用经验中的修复方法
        applied_fixes = []
        for exp in experience:
            if exp.get('task_type') == 'fix_bug':
                fix_method = exp.get('context', {}).get('fix_method')
                if fix_method:
                    applied_fixes.append(fix_method)
        
        # 生成修复
        fixed_code, fix_description = self._apply_fix(
            code_content, 
            error_analysis,
            applied_fixes
        )
        
        if fixed_code and file_path:
            # 写入修复后的代码
            file_path.write_text(fixed_code, encoding='utf-8')
            logger.info(f"修复代码已写入: {file_path}")
            files_modified.append(str(file_path))
        
        # 如果 fixed_code 为 None，表示自动修复未实际修改代码
        actually_fixed = fixed_code is not None and fixed_code != code_content
        
        # Bug#47修复: learnings应与success一致
        if actually_fixed:
            fix_learning = f"Bug修复成功: {fix_description}"
        else:
            fix_learning = f"Bug修复失败: {fix_description}（自动修复未生效，需手动处理）"
        
        return TaskResult(
            success=actually_fixed,
            output={
                "fix_description": fix_description,
                "error_analysis": error_analysis,
                "files_modified": files_modified
            },
            learnings=[fix_learning],
            files_modified=files_modified
        )
    
    def _analyze_error(self, error_message: str, code: str) -> Dict[str, Any]:
        """分析错误信息"""
        analysis = {
            "error_type": "unknown",
            "line_number": None,
            "suggestions": []
        }
        
        # Python错误模式
        patterns = [
            (r'(\w+Error): (.+) at line (\d+)', 'python'),
            (r'File "([^"]+)", line (\d+)', 'python'),
            (r'SyntaxError: (.+)', 'python_syntax'),
            (r'TypeError: (.+)', 'python_type'),
            (r'NameError: name \'(\w+)\' is not defined', 'python_name'),
        ]
        
        for pattern, error_type in patterns:
            match = re.search(pattern, error_message)
            if match:
                analysis["error_type"] = error_type
                analysis["matched"] = match.groups()
                break
        
        return analysis
    
    def _apply_fix(
        self,
        code: str,
        error_analysis: Dict[str, Any],
        applied_fixes: List[str]
    ) -> Tuple[Optional[str], str]:
        """应用修复
        
        注意：当前实现为占位逻辑，实际修复需要结合LLM或规则引擎。
        返回 (None, description) 表示无法自动修复。
        """
        error_type = error_analysis.get("error_type", "unknown")
        
        fix_description = f"分析 {error_type} 类型的错误（自动修复待实现）"
        
        # 根据错误类型应用不同修复策略
        if error_type == "python_name":
            matched = error_analysis.get("matched", [])
            if matched:
                var_name = matched[0] if matched else "unknown"
                fix_description = f"检测到未定义变量: {var_name}（需手动修复）"
        
        elif error_type == "python_syntax":
            fix_description = "检测到语法错误（需手动修复）"
        
        # 返回 None 表示代码未被修改（占位实现）
        return None, fix_description
    
    def _implement(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """实现功能"""
        from ..core.engine import TaskResult
        
        context = task.context
        description = task.description
        
        files_modified = []
        
        # 基于经验生成实现
        similar_implementations = [
            exp for exp in experience 
            if exp.get('task_type') in ['implement', 'add_feature']
        ]
        
        # 创建实现文件
        output_file = context.get('output_file')
        if output_file:
            output_path = self.workspace / output_file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 生成代码框架
            code = self._generate_code(description, similar_implementations)
            output_path.write_text(code, encoding='utf-8')
            logger.info(f"实现文件已创建: {output_path}")
            files_modified.append(str(output_path))
        
        return TaskResult(
            success=True,
            output={
                "implementation": description,
                "files_modified": files_modified,
                "similar_implementations": len(similar_implementations)
            },
            learnings=[f"实现完成: {description[:50]}"],
            files_modified=files_modified
        )
    
    def _generate_code(
        self,
        description: str,
        similar_implementations: List[Dict]
    ) -> str:
        """生成代码"""
        # 基础代码模板
        template = '''#!/usr/bin/env python3
"""
{description}
自动生成于 ContinuousAgent
"""

def main():
    """主函数"""
    # TODO: 实现具体逻辑
    pass

if __name__ == "__main__":
    main()
'''
        return template.format(description=description)
    
    def _refactor(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """重构代码"""
        from ..core.engine import TaskResult
        
        context = task.context
        file_path = context.get('file_path')
        
        files_modified = []
        summary = "重构完成"
        
        if file_path:
            file_path = Path(file_path)
            if file_path.exists():
                code = file_path.read_text(encoding='utf-8')
                
                # 应用重构
                refactored_code = self._apply_refactoring(code, experience)
                
                if refactored_code != code:
                    file_path.write_text(refactored_code, encoding='utf-8')
                    files_modified.append(str(file_path))
                    summary = "代码已重构并保存"
                    logger.info(f"重构完成: {file_path}")
        
        return TaskResult(
            success=True,
            output={
                "summary": summary,
                "files_modified": files_modified
            },
            learnings=[summary],
            files_modified=files_modified
        )
    
    def _apply_refactoring(self, code: str, experience: List[Dict]) -> str:
        """应用重构"""
        # 基本重构：清理多余空行
        lines = code.split('\n')
        cleaned_lines = []
        prev_empty = False
        
        for line in lines:
            is_empty = line.strip() == ''
            if is_empty and prev_empty:
                continue
            cleaned_lines.append(line)
            prev_empty = is_empty
        
        return '\n'.join(cleaned_lines)
    
    def _add_feature(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """添加新功能"""
        from ..core.engine import TaskResult
        
        # 与implement类似，但更专注于添加到现有代码
        result = self._implement(task, experience)
        # 安全设置 feature_type，避免 output 为 None 时崩溃
        if result.output is None:
            result.output = {}
        result.output["feature_type"] = "new_feature"
        return result
    
    def _optimize(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """优化代码"""
        from ..core.engine import TaskResult
        
        context = task.context
        file_path = context.get('file_path')
        
        files_modified = []
        optimizations = []
        
        if file_path:
            file_path = Path(file_path)
            if file_path.exists():
                code = file_path.read_text(encoding='utf-8')
                
                # 应用优化
                optimized_code, applied_optimizations = self._apply_optimizations(code)
                
                if optimized_code != code:
                    file_path.write_text(optimized_code, encoding='utf-8')
                    files_modified.append(str(file_path))
                    optimizations = applied_optimizations
                    logger.info(f"优化完成: {file_path}，应用 {len(optimizations)} 项优化")
        
        # Bug#53修复: 没有实际优化时返回success=False
        has_actual_optimization = bool(optimizations) or bool(files_modified)
        
        return TaskResult(
            success=has_actual_optimization,
            output={
                "optimizations": optimizations,
                "files_modified": files_modified
            },
            learnings=optimizations if has_actual_optimization else ["优化未生效: 未找到可优化的代码或未提供文件路径"],
            files_modified=files_modified
        )
    
    def _apply_optimizations(self, code: str) -> Tuple[str, List[str]]:
        """应用优化"""
        optimizations = []
        
        # 优化1：移除未使用的导入（简单检测）
        import_lines = []
        other_lines = []
        for line in code.split('\n'):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                import_lines.append(line)
            else:
                other_lines.append(line)
        
        # 优化2：简化条件表达式
        # （这里可以添加更多优化规则）
        
        return code, optimizations
    
    def _document(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """生成文档"""
        from ..core.engine import TaskResult
        
        context = task.context
        file_path = context.get('file_path')
        description = task.description
        
        doc_content = f"# 文档: {description}\n\n"
        doc_content += f"## 概述\n\n{description}\n\n"
        doc_content += f"## 相关经验\n\n"
        
        for exp in experience[:5]:
            doc_content += f"- {exp.get('content', str(exp))}\n"
        
        doc_content += f"\n## 备注\n\n自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        files_modified = []
        if file_path:
            output_path = Path(file_path).with_suffix('.md')
            output_path.write_text(doc_content, encoding='utf-8')
            logger.info(f"文档已生成: {output_path}")
            files_modified.append(str(output_path))
        
        return TaskResult(
            success=True,
            output={
                "doc_content": doc_content,
                "files_modified": files_modified
            },
            learnings=[f"文档生成: {description[:50]}"],
            files_modified=files_modified
        )
    
    def _test(self, task: Any, experience: List[Dict[str, Any]]) -> Any:
        """执行测试"""
        from ..core.engine import TaskResult
        
        context = task.context
        test_command = context.get('test_command', 'pytest')
        test_file = context.get('test_file')
        
        results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # 执行测试命令
            logger.info(f"执行测试命令: {test_command}")
            result = subprocess.run(
                test_command.split(),
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output = result.stdout + result.stderr
            
            # 解析测试结果
            if 'passed' in output.lower():
                match = re.search(r'(\d+)\s+passed', output)
                if match:
                    results["passed"] = int(match.group(1))
            
            if 'failed' in output.lower():
                match = re.search(r'(\d+)\s+failed', output)
                if match:
                    results["failed"] = int(match.group(1))
            
            return TaskResult(
                success=result.returncode == 0,
                output={
                    "test_results": results,
                    "output": output
                },
                learnings=[f"测试完成: {results['passed']} 通过, {results['failed']} 失败"]
            )
            
        except subprocess.TimeoutExpired:
            logger.error(f"测试执行超时 (300s)，命令: {test_command}")
            return TaskResult(
                success=False,
                error="测试执行超时"
            )
        except Exception as e:
            logger.error(f"测试执行异常: {e}")
            return TaskResult(
                success=False,
                error=str(e)
            )
    
    def _detect_language(self, extension: str) -> str:
        """检测编程语言"""
        for lang, extensions in self.SUPPORTED_LANGUAGES.items():
            if extension in extensions:
                return lang
        return 'unknown'
    
    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 300
    ) -> Tuple[int, str, str]:
        """
        执行shell命令
        
        Returns:
            (return_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or str(self.workspace),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        total = len(self.execution_history)
        successful = sum(1 for h in self.execution_history if h.get('success'))
        
        return {
            "total_executions": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0
        }
