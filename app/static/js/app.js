// 小说自动工厂 - 通用交互

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-confirm], .btn-danger').forEach(element => {
        element.addEventListener('click', event => {
            if (element.disabled) return;
            const message = element.dataset.confirm || '确定要执行此操作吗？';
            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            const button = form.querySelector('button[type="submit"][data-generate], button[type="submit"].btn-primary, button[type="submit"].btn-success');
            if (!button || button.disabled) return;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = '提交中...';
            button.disabled = true;
            setTimeout(() => {
                if (button.disabled && button.dataset.originalText) {
                    button.innerHTML = button.dataset.originalText;
                    button.disabled = false;
                }
            }, 10000);
        });
    });

    const taskCard = document.querySelector('[data-task-card]');
    if (taskCard) {
        const taskId = taskCard.dataset.taskId;
        const poll = setInterval(() => {
            fetch(`/api/tasks/${taskId}`)
                .then(response => response.json())
                .then(data => {
                    const bar = taskCard.querySelector('[data-progress-bar]');
                    const label = taskCard.querySelector('[data-progress-label]');
                    const status = taskCard.querySelector('[data-task-status]');
                    const step = taskCard.querySelector('[data-current-step]');
                    if (bar) bar.style.width = `${data.progress || 0}%`;
                    if (label) label.textContent = `${data.progress || 0}%`;
                    if (status) status.textContent = data.status;
                    if (step) step.textContent = data.current_step || data.status;
                    if (['success', 'failed', 'cancelled'].includes(data.status)) {
                        clearInterval(poll);
                        window.location.reload();
                    }
                })
                .catch(() => clearInterval(poll));
        }, 4000);
    }

    const flowCard = document.querySelector('[data-flow-card]');
    if (flowCard) {
        const taskId = flowCard.dataset.taskId;
        const renderFlow = data => {
            const bar = flowCard.querySelector('[data-flow-progress-bar]');
            const label = flowCard.querySelector('[data-flow-progress-label]');
            const status = flowCard.querySelector('[data-flow-status]');
            const current = flowCard.querySelector('[data-flow-current]');
            const steps = flowCard.querySelector('[data-flow-steps]');
            if (bar) bar.style.width = `${data.progress || 0}%`;
            if (label) label.textContent = `${data.progress || 0}%`;
            if (status) status.textContent = data.status;
            if (current) current.textContent = data.current_step || data.status;
            if (steps && Array.isArray(data.steps) && data.steps.length) {
                steps.innerHTML = data.steps.map(step => {
                    const order = String((step.step_order ?? 0) + 1).padStart(2, '0');
                    const model = step.model_name ? ` · ${escapeHTML(step.model_name)}` : '';
                    return `
                        <a class="flow-step ${flowStepClass(step.status)}" href="/tasks/${data.id}">
                            <span>${order}</span>
                            <strong>${escapeHTML(step.step_name || '')}</strong>
                            <small>${escapeHTML(step.status || '')}${model}</small>
                        </a>
                    `;
                }).join('');
            }
            return data.status;
        };

        fetch(`/api/tasks/${taskId}`)
            .then(response => response.json())
            .then(data => {
                const status = renderFlow(data);
                if (['pending', 'running'].includes(status)) {
                    const poll = setInterval(() => {
                        fetch(`/api/tasks/${taskId}`)
                            .then(response => response.json())
                            .then(next => {
                                const nextStatus = renderFlow(next);
                                if (['success', 'failed', 'cancelled'].includes(nextStatus)) {
                                    clearInterval(poll);
                                }
                            })
                            .catch(() => clearInterval(poll));
                    }, 4000);
                }
            })
            .catch(() => {});
    }
});

function escapeHTML(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function flowStepClass(status) {
    if (status === 'success') return 'success';
    if (status === 'failed') return 'failed';
    if (status === 'running') return 'running';
    return '';
}

function handleExport(btn) {
    if (!confirm('确定要导出整本小说吗？')) return false;
    btn.innerHTML = '导出中...';
    btn.disabled = true;
    return true;
}
