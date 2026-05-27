// 小说自动工厂 - 前端交互脚本

document.addEventListener('DOMContentLoaded', function() {
    // 给所有危险操作按钮添加确认提示
    const dangerButtons = document.querySelectorAll('.btn-danger, [data-confirm]');
    dangerButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            const message = btn.dataset.confirm || '确定要执行此操作吗？';
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });

    // 生成类按钮点击后显示“处理中”状态
    const generateButtons = document.querySelectorAll('.btn-generate, [data-generate]');
    generateButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const originalText = btn.innerHTML;
            btn.innerHTML = '处理中，请稍候...';
            btn.disabled = true;

            // 5秒后如果页面没跳转，恢复按钮（防止卡死）
            setTimeout(() => {
                if (btn.disabled) {
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }
            }, 8000);
        });
    });

    // 状态徽章自动着色（如果后端没处理）
    document.querySelectorAll('.status-text').forEach(el => {
        const text = el.textContent.trim();
        if (text.includes('运行')) el.className = 'badge badge-running';
        else if (text.includes('暂停')) el.className = 'badge badge-paused';
        else if (text.includes('失败')) el.className = 'badge badge-failed';
        else if (text.includes('完成')) el.className = 'badge badge-success';
        else el.className = 'badge badge-draft';
    });
});

// 导出按钮特殊处理
function handleExport(btn, novelId) {
    if (!confirm('确定要导出整本小说吗？')) return false;
    
    const originalText = btn.innerHTML;
    btn.innerHTML = '导出中...';
    btn.disabled = true;
    
    // 实际由后端处理，这里只是UI反馈
    return true;
}