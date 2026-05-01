/**
 * AI办公室 — Frontend App (Vue 3)
 * 实时多智能体协作可视化
 */
const { createApp, ref, computed, onMounted, nextTick } = Vue;

// 服务器地址（自动检测）
const API_BASE = `http://${window.location.hostname}:${window.location.port || 8000}`;
const WS_URL = `ws://${window.location.hostname}:${window.location.port || 8000}/ws`;

createApp({
    setup() {
        // --- State ---
        const agents = ref({});
        const messages = ref([]);
        const inputMessage = ref("");
        const inputEl = ref(null);
        const mentionOpen = ref(false);
        const mentionIndex = ref(0);
        const mentionStart = ref(-1);
        const mentionQuery = ref("");
        const lastMentionQuery = ref("");
        const currentTask = ref(null);
        const officeRegistry = ref({ agents: {}, workflow_map: [] });
        const selectedAgentId = ref("aiky_main");
        const expandedMessages = ref({});
        const showAgentProfile = ref(false);
        const learningInProgress = ref(false);
        const lastLearningRoute = ref(null);

        // History
        const showHistory = ref(false);      // 显示历史列表二级页
        const historyList = ref([]);
        const viewingHistory = ref(false);   // 正在查看某条历史对话
        const viewingHistoryTitle = ref(''); // 当前查看的历史对话标题

        // 历史记录按日期分组
        const groupedHistory = computed(() => {
            const groups = [];
            const now = new Date();
            const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const yesterdayStart = new Date(todayStart - 86400000);
            const weekStart = new Date(todayStart - 6 * 86400000);

            const buckets = { today: [], yesterday: [], week: [], earlier: [] };

            for (const conv of historyList.value) {
                const d = new Date(conv.created_at);
                if (d >= todayStart) buckets.today.push(conv);
                else if (d >= yesterdayStart) buckets.yesterday.push(conv);
                else if (d >= weekStart) buckets.week.push(conv);
                else buckets.earlier.push(conv);
            }

            if (buckets.today.length) groups.push({ label: '今天', items: buckets.today });
            if (buckets.yesterday.length) groups.push({ label: '昨天', items: buckets.yesterday });
            if (buckets.week.length) groups.push({ label: '本周', items: buckets.week });
            if (buckets.earlier.length) groups.push({ label: '更早', items: buckets.earlier });
            return groups;
        });

        // Modal
        const showModal = ref(false);
        const modalTitle = ref("");
        const modalPath = ref("");
        const modalRawContent = ref("");
        const isHtmlPreview = ref(false);
        const previewUrl = ref("");
        const modalRenderedContent = computed(() => {
            try {
                if (typeof marked !== 'undefined' && marked.parse) {
                    return marked.parse(modalRawContent.value);
                }
                // 简易 markdown 渲染后备方案
                return modalRawContent.value
                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                    .replace(/^### (.*?)$/gm, '<h3>$1</h3>')
                    .replace(/^## (.*?)$/gm, '<h2>$1</h2>')
                    .replace(/^# (.*?)$/gm, '<h1>$1</h1>')
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
                    .replace(/`(.*?)`/g, '<code>$1</code>')
                    .replace(/\n/g, '<br>');
            } catch {
                return `<pre>${modalRawContent.value}</pre>`;
            }
        });

        // Workflow stages
        const defaultStages = [
            { key: "research", label: "调研" },
            { key: "competitive", label: "竞品" },
            { key: "planning", label: "PRD" },
            { key: "architecture", label: "架构" },
            { key: "execution", label: "开发" },
            { key: "testing", label: "测试" },
        ];

        const stages = computed(() => {
            const workflowMap = officeRegistry.value.workflow_map || [];
            const stageKeys = ["research", "competitive", "planning", "architecture", "execution", "testing"];
            const selected = currentTask.value?.selected_stages || [];
            if (selected.length) {
                return selected.map((key) => {
                    const step = workflowMap.find((item) => item.key === key);
                    const fallback = defaultStages.find((item) => item.key === key);
                    return { key, label: step?.label || fallback?.label || key };
                });
            }
            const mapped = workflowMap
                .filter((step) => stageKeys.includes(step.key))
                .map((step) => ({ key: step.key, label: step.label }));
            return mapped.length ? mapped : defaultStages;
        });

        const stageOrder = computed(() => ["none", ...stages.value.map((s) => s.key), "completed"]);

        const currentStage = computed(() => {
            if (!currentTask.value) return "none";
            return currentTask.value.approval_stage || "none";
        });

        const canStopTask = computed(() => {
            if (!currentTask.value) return false;
            return ["pending", "in_progress", "waiting_for_confirm", "paused"].includes(currentTask.value.status);
        });

        const isStageComplete = (stageKey) => {
            const current = stageOrder.value.indexOf(currentStage.value);
            const target = stageOrder.value.indexOf(stageKey);
            return current > target;
        };

        // --- Helpers ---
        const statusTextMap = {
            pending: "等待开始",
            analyzing: "分析意图",
            waiting_for_confirm: "等待审批",
            in_progress: "执行中",
            completed: "已完成",
            failed: "已终止",
            stopped: "已停止",
        };

        const getStatusText = (s) => statusTextMap[s] || s;

        const pixelAvatar = (p) => {
            const bg = p.bg || p.shirt;
            const hairSvg = (() => {
                if (p.style === "braids") return `
                    <rect x="7" y="4" width="18" height="5" fill="${p.hair}"/>
                    <rect x="5" y="9" width="5" height="12" fill="${p.hair}"/>
                    <rect x="22" y="9" width="5" height="12" fill="${p.hair2}"/>
                    <rect x="5" y="13" width="3" height="2" fill="#E8B663"/>
                    <rect x="24" y="15" width="3" height="2" fill="#E8B663"/>
                    <rect x="6" y="18" width="3" height="2" fill="${p.hair2}"/>
                    <rect x="23" y="19" width="3" height="2" fill="${p.hair}"/>
                    <rect x="10" y="5" width="5" height="2" fill="#F0BE67"/>`;
                if (p.style === "asymBob") return `
                    <rect x="7" y="5" width="18" height="5" fill="${p.hair}"/>
                    <rect x="5" y="10" width="5" height="8" fill="${p.hair2}"/>
                    <rect x="21" y="9" width="6" height="12" fill="${p.hair}"/>
                    <rect x="17" y="6" width="8" height="3" fill="${p.hair2}"/>
                    <rect x="8" y="10" width="5" height="1" fill="#2A2B35"/>`;
                if (p.style === "shortFlip") return `
                    <rect x="7" y="5" width="17" height="4" fill="${p.hair}"/>
                    <rect x="5" y="9" width="6" height="6" fill="${p.hair2}"/>
                    <rect x="21" y="9" width="5" height="6" fill="${p.hair}"/>
                    <rect x="4" y="14" width="5" height="3" fill="${p.hair}"/>
                    <rect x="23" y="13" width="5" height="3" fill="${p.hair2}"/>
                    <rect x="11" y="4" width="8" height="2" fill="#FF6A2E"/>`;
                return `
                    <rect x="7" y="5" width="18" height="4" fill="${p.hair}"/>
                    <rect x="5" y="9" width="22" height="5" fill="${p.hair}"/>
                    <rect x="5" y="13" width="4" height="7" fill="${p.hair2}"/>
                    <rect x="23" y="13" width="4" height="7" fill="${p.hair2}"/>`;
            })();
            const svg = p.robot ? `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" shape-rendering="crispEdges">
                    <rect width="32" height="32" fill="${bg}"/>
                    <rect x="7" y="5" width="18" height="4" fill="${p.outline}"/>
                    <rect x="5" y="9" width="22" height="12" fill="${p.outline}"/>
                    <rect x="8" y="8" width="16" height="14" fill="${p.shirt}"/>
                    <rect x="10" y="12" width="4" height="3" fill="${p.eye}"/>
                    <rect x="18" y="12" width="4" height="3" fill="${p.eye}"/>
                    <rect x="13" y="18" width="6" height="2" fill="${p.mouth}"/>
                    <rect x="9" y="23" width="14" height="5" fill="${p.shirt2}"/>
                    <rect x="4" y="15" width="3" height="6" fill="${p.shirt2}"/>
                    <rect x="25" y="15" width="3" height="6" fill="${p.shirt2}"/>
                </svg>` : `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" shape-rendering="crispEdges">
                    <rect width="32" height="32" fill="${bg}"/>
                    ${hairSvg}
                    <rect x="9" y="11" width="14" height="12" fill="${p.skin}"/>
                    <rect x="10" y="21" width="12" height="3" fill="${p.skin2}"/>
                    <rect x="11" y="15" width="3" height="2" fill="#1a1a2a"/>
                    <rect x="18" y="15" width="3" height="2" fill="#1a1a2a"/>
                    <rect x="14" y="20" width="4" height="1" fill="${p.mouth || '#c04030'}"/>
                    <rect x="7" y="24" width="18" height="6" fill="${p.shirt}"/>
                    <rect x="7" y="28" width="18" height="2" fill="${p.shirt2}"/>
                </svg>`;
            return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
        };

        const avatarMap = {
            aiky_main: pixelAvatar({ robot: true, bg: "#1c1c30", outline: "#818cf8", shirt: "#6366f1", shirt2: "#4f52c4", eye: "#00eeff", mouth: "#00ff88" }),
            ceo_01: pixelAvatar({ bg: "#2C3E7B", hair: "#B8793A", hair2: "#7E4A22", skin: "#FDBCB4", skin2: "#E8A090", shirt: "#2F6FA7", shirt2: "#1D4E78" }),
            pm_01: pixelAvatar({ bg: "#4A1560", hair: "#D89A4A", hair2: "#9B5B28", skin: "#FDBCB4", skin2: "#E8A090", shirt: "#9333EA", shirt2: "#7928C8", style: "braids" }),
            cto_01: pixelAvatar({ bg: "#0E7490", hair: "#1a1a2a", hair2: "#0a0a18", skin: "#C68642", skin2: "#A06830", shirt: "#0E7490", shirt2: "#0A5A70", mouth: "#803020" }),
            ui_01: pixelAvatar({ bg: "#DB2777", hair: "#171820", hair2: "#07080D", skin: "#F1C27D", skin2: "#D4A860", shirt: "#DB2777", shirt2: "#B81F62", style: "asymBob" }),
            fe_01: pixelAvatar({ bg: "#2563EB", hair: "#F2F2EA", hair2: "#BFC1C8", skin: "#C68642", skin2: "#A06830", shirt: "#E6EEF3", shirt2: "#B9C8D2", mouth: "#803020" }),
            be_01: pixelAvatar({ bg: "#059669", hair: "#5C3800", hair2: "#3A2200", skin: "#FDBCB4", skin2: "#E8A090", shirt: "#059669", shirt2: "#047857" }),
            qa_01: pixelAvatar({ bg: "#DC2626", hair: "#E43B18", hair2: "#8F1A0B", skin: "#F1C27D", skin2: "#D4A860", shirt: "#DC2626", shirt2: "#B91C1C", style: "shortFlip" }),
        };

        const nameMap = {
            ceo_01: "Steve (CEO)",
            cto_01: "Elon (CTO)",
            aiky_main: "AI办公室",
            pm_01: "Emma (PM)",
            ui_01: "Alex (UI)",
            fe_01: "Lucas (前端)",
            be_01: "David (后端)",
            qa_01: "Sarah (QA)",
        };

        const getAvatar = (id) => avatarMap[id] || null;
        const getAgentName = (id) => nameMap[id] || (agents.value[id]?.name || id);

        const agentOrder = ["aiky_main", "ceo_01", "pm_01", "cto_01", "ui_01", "fe_01", "be_01", "qa_01"];
        const mentionAliasMap = {
            aiky_main: "aiky",
            ceo_01: "steve",
            pm_01: "emma",
            cto_01: "elon",
            ui_01: "alex",
            fe_01: "lucas",
            be_01: "david",
            qa_01: "sarah",
        };

        const getCapability = (id) => {
            const stateProfile = agents.value[id]?.capability || {};
            if (Object.keys(stateProfile).length) return stateProfile;
            if (id === officeRegistry.value.brain?.id) return officeRegistry.value.brain || {};
            return (officeRegistry.value.agents || {})[id] || {};
        };

        const officeAgents = computed(() => {
            const ids = new Set([...agentOrder, ...Object.keys(agents.value || {})]);
            return Array.from(ids)
                .filter((id) => agents.value[id] || getCapability(id).name)
                .map((id) => ({
                    id,
                    state: agents.value[id] || {},
                    capability: getCapability(id),
                }));
        });

        const mentionAgents = computed(() => {
            const ids = new Set([...agentOrder, ...Object.keys(agents.value || {})]);
            return Array.from(ids)
                .filter((id) => id !== "aiky_main" && (agents.value[id] || getCapability(id).name || nameMap[id]))
                .map((id) => {
                    const capability = getCapability(id);
                    const label = capability.name || getAgentName(id).replace(/\s*\(.*?\)\s*/g, "");
                    return {
                        id,
                        alias: mentionAliasMap[id] || label.toLowerCase(),
                        name: label,
                        title: capability.title || agents.value[id]?.role || getAgentName(id),
                    };
                });
        });

        const mentionCandidates = computed(() => {
            const q = mentionQuery.value.trim().toLowerCase();
            if (!q) return mentionAgents.value;
            return mentionAgents.value.filter((agent) => {
                return agent.alias.toLowerCase().includes(q)
                    || agent.name.toLowerCase().includes(q)
                    || String(agent.title || "").toLowerCase().includes(q);
            });
        });

        const selectedAgent = computed(() => {
            const id = selectedAgentId.value;
            return {
                id,
                state: agents.value[id] || {},
                capability: getCapability(id),
            };
        });

        const selectAgent = (id) => {
            if (selectedAgentId.value === id && showAgentProfile.value) {
                showAgentProfile.value = false;
                return;
            }
            selectedAgentId.value = id;
            showAgentProfile.value = true;
        };

        const hideAgentProfile = () => {
            showAgentProfile.value = false;
        };

        const getWorkflowOwner = (stageKey) => {
            const step = (officeRegistry.value.workflow_map || []).find((item) => item.key === stageKey);
            return step ? getAgentName(step.owner) : "";
        };

        const getAction = (id) => {
            const a = agents.value[id];
            if (!a || a.status === "idle") return "空闲";
            return a.current_action || a.status;
        };

        const getCardClass = (id) => {
            const a = agents.value[id];
            if (!a) return "";
            return a.status !== "idle" ? a.status : "";
        };

        const renderMarkdown = (content) => {
            try {
                // Simple inline markdown: bold, emoji, newlines
                return content
                    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                    .replace(/\n/g, "<br>");
            } catch {
                return content;
            }
        };

        const isOperationalMessage = (msg) => {
            if (!msg || msg.sender_id === "user" || msg.message_type === "artifact") return false;
            if (!["aiky_main", "system"].includes(msg.sender_id)) return false;
            const content = msg.content || "";
            return [
                "📚", "📌", "📋", "🚀", "👍", "⏭️", "🔄",
                "已读取", "把材料读进来", "交给", "强制指派", "指令分析完成", "把流程拆好了", "阶段",
            ].some((token) => content.includes(token));
        };

        const friendlyMessage = (msg) => {
            const content = msg.content || "";
            if (content.includes("已读取") || content.includes("把材料读进来")) return "老大，材料我读进来了。";
            const assignMatch = content.match(/交给\s+\*\*([^*]+)\*\*/)
                || content.match(/指派给\s+\*\*([^*]+)\*\*/);
            if (assignMatch) return `老大，我安排好了，${assignMatch[1]} 会直接处理。`;
            const stageMatch = content.match(/阶段\s+\d+\/\d+：([^*\\n]+)/);
            if (stageMatch) return `老大，进入${stageMatch[1].trim()}了。`;
            if (content.includes("指令分析完成") || content.includes("把流程拆好了")) return "老大，我把流程拆好了。";
            if (content.includes("批准") || content.includes("继续推进")) return "收到，我继续往下推进。";
            if (content.includes("跳过") || content.includes("直接进入")) return "收到，我按你说的阶段走。";
            return content.split("\n")[0].slice(0, 36) || "处理中...";
        };

        const isMessageExpanded = (msg) => !!expandedMessages.value[msg.id];
        const toggleMessageDetails = (msg) => {
            expandedMessages.value = {
                ...expandedMessages.value,
                [msg.id]: !expandedMessages.value[msg.id],
            };
        };

        const shouldRouteToEvolution = (content) => {
            const text = content.trim().toLowerCase();
            if (!text) return false;
            if (/^\/(learn|evolve)\b/i.test(text) || /^\/(学习|进化)/.test(text)) return true;

            const names = ["aiky", "steve", "emma", "elon", "alex", "lucas", "david", "sarah", "ceo", "cto", "pm", "ui", "前端", "后端", "qa", "测试"];
            const learningTerms = ["进化", "学习", "学一下", "记住", "沉淀", "复盘", "反馈", "经验", "方法", "下次", "以后"];
            const hasName = names.some((name) => text.includes(name));
            const hasLearningTerm = learningTerms.some((term) => text.includes(term));
            if (hasName && hasLearningTerm) return true;

            return [
                /员工.*(学习|进化|沉淀|复盘)/,
                /让.*(学|学习|记住|进化)/,
                /(这条|这个|这些).*(经验|方法|反馈|复盘)/,
                /(以后|下次).*(应该|不要|需要|优先|避免)/,
                /(方法|经验).*沉淀/,
            ].some((pattern) => pattern.test(text));
        };

        // --- WebSocket ---
        let socket = null;

        const connectWebSocket = () => {
            socket = new WebSocket(WS_URL);

            socket.onopen = () => console.log("[WS] Connected");

            socket.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    handleEvent(msg);
                } catch (e) {
                    console.error("[WS] Parse error:", e);
                }
            };

            socket.onclose = () => {
                console.log("[WS] Disconnected. Reconnecting...");
                setTimeout(connectWebSocket, 3000);
            };
        };

        const handleEvent = (event) => {
            if (event.type === "state_update") {
                // 全量状态更新
                agents.value = event.data.agents || {};

                // 找当前活跃任务
                const tasks = event.data.tasks || {};
                const ids = Object.keys(tasks);
                const activeId = ids.reverse().find(
                    (id) => !['completed', 'failed', 'stopped'].includes(tasks[id].status)
                );
                currentTask.value = activeId ? tasks[activeId] : null;

                // 从全量状态同步消息（防止 WebSocket 重连后丢失历史消息）
                const serverMessages = event.data.messages || [];
                if (serverMessages.length > messages.value.filter(m => m.sender_id !== 'user').length) {
                    const shouldFollow = isChatNearBottom();
                    // 保留用户消息，合并服务器消息
                    const existingIds = new Set(messages.value.map(m => m.id));
                    let addedCount = 0;
                    for (const msg of serverMessages) {
                        if (!existingIds.has(msg.id)) {
                            messages.value.push(msg);
                            addedCount += 1;
                        }
                    }
                    if (addedCount > 0) scrollToBottomIfNeeded(shouldFollow);
                }

                // 同步所有 Agent 状态到 Pixel Office
                if (window.pixelOffice) {
                    for (const [id, state] of Object.entries(agents.value)) {
                        window.pixelOffice.setAgentState(id, state.status, state.current_action || '');
                    }
                }

            } else if (event.type === "new_message") {
                // 实时消息推送
                const msg = event.data;
                // 防重复
                if (!messages.value.find((m) => m.id === msg.id)) {
                    appendMessage(msg);
                }
            } else if (event.type === "agent_status") {
                // 单个 Agent 状态更新
                const id = event.agent_id;
                if (agents.value[id]) {
                    agents.value[id].status = event.status;
                    agents.value[id].current_action = event.action || "";
                }
                // 实时推送到 Pixel Office
                if (window.pixelOffice) {
                    window.pixelOffice.setAgentState(id, event.status, event.action || '');
                }
            }
        };

        const closeMention = () => {
            mentionOpen.value = false;
            mentionIndex.value = 0;
            mentionStart.value = -1;
            mentionQuery.value = "";
            lastMentionQuery.value = "";
        };

        const updateMentionState = () => {
            const el = inputEl.value;
            if (!el) return;
            const cursor = el.selectionStart ?? inputMessage.value.length;
            const before = inputMessage.value.slice(0, cursor);
            const match = before.match(/(^|[\s，,。；;：:])@([a-zA-Z\u4e00-\u9fff]*)$/);
            if (!match) {
                closeMention();
                return;
            }
            mentionStart.value = before.length - match[2].length - 1;
            const nextQuery = match[2] || "";
            if (nextQuery !== lastMentionQuery.value) {
                mentionIndex.value = 0;
                lastMentionQuery.value = nextQuery;
            }
            mentionQuery.value = nextQuery;
            mentionOpen.value = true;
            if (mentionIndex.value >= mentionCandidates.value.length) {
                mentionIndex.value = Math.max(0, mentionCandidates.value.length - 1);
            }
        };

        const handleInputChange = () => {
            nextTick(updateMentionState);
        };

        const selectMention = (agent) => {
            const el = inputEl.value;
            if (!el || !agent) return;
            const cursor = el.selectionStart ?? inputMessage.value.length;
            const start = mentionStart.value >= 0 ? mentionStart.value : cursor;
            const before = inputMessage.value.slice(0, start);
            const after = inputMessage.value.slice(cursor);
            const insert = `@${agent.alias}`;
            const needsSpace = after.length > 0 && !/^[\s，,。；;：:]/.test(after) ? " " : "";
            inputMessage.value = `${before}${insert}${needsSpace}${after}`;
            const nextPos = before.length + insert.length + (needsSpace ? 1 : 0);
            closeMention();
            nextTick(() => {
                el.focus();
                el.setSelectionRange(nextPos, nextPos);
            });
        };

        const scrollMentionActiveIntoView = () => {
            nextTick(() => {
                const active = document.querySelector(".mention-item.active");
                if (active && active.scrollIntoView) {
                    active.scrollIntoView({ block: "nearest" });
                }
            });
        };

        const handleInputKeydown = (event) => {
            if (mentionOpen.value) {
                if (event.key === "ArrowDown") {
                    event.preventDefault();
                    const count = mentionCandidates.value.length || 1;
                    mentionIndex.value = (mentionIndex.value + 1) % count;
                    scrollMentionActiveIntoView();
                    return;
                }
                if (event.key === "ArrowUp") {
                    event.preventDefault();
                    const count = mentionCandidates.value.length || 1;
                    mentionIndex.value = (mentionIndex.value - 1 + count) % count;
                    scrollMentionActiveIntoView();
                    return;
                }
                if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    const agent = mentionCandidates.value[mentionIndex.value];
                    if (agent) selectMention(agent);
                    return;
                }
                if (event.key === "Escape") {
                    event.preventDefault();
                    closeMention();
                    return;
                }
            }

            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        };

        // --- User Actions ---
        const sendMessage = async () => {
            const content = inputMessage.value.trim();
            if (!content) return;
            closeMention();
            inputMessage.value = "";
            const userMessageId = "user_" + Date.now();

            // 乐观 UI
            appendMessage({
                id: userMessageId,
                sender_id: "user",
                content: content,
                timestamp: new Date().toISOString(),
                message_type: "text",
            }, { forceScroll: true });

            if (shouldRouteToEvolution(content)) {
                learningInProgress.value = true;
                try {
                    const res = await fetch(`${API_BASE}/api/evolution/learn`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ content, message_id: userMessageId }),
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || "Learning route failed");
                    lastLearningRoute.value = data;
                    appendMessage({
                        id: "learn_route_" + Date.now(),
                        sender_id: "aiky_main",
                        content: `老大，我把这条学习内容交给 ${data.agent_name}${data.agent_title ? `（${data.agent_title}）` : ""} 了。\n记录编号：${data.record_id}`,
                        timestamp: new Date().toISOString(),
                        message_type: "text",
                    });
                } catch (e) {
                    console.error("Learning API Error:", e);
                    appendMessage({
                        id: "learn_err_" + Date.now(),
                        sender_id: "system",
                        content: "⚠️ 进化学习记录失败，请确认后端服务和 AI办公室 learning 目录可写。",
                        message_type: "text",
                    });
                } finally {
                    learningInProgress.value = false;
                }
                return;
            }

            try {
                await fetch(`${API_BASE}/api/tasks/create`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        title: content.substring(0, 30),
                        description: content,
                        message_id: userMessageId,
                    }),
                });
            } catch (e) {
                console.error("API Error:", e);
                appendMessage({
                    id: "err_" + Date.now(),
                    sender_id: "system",
                    content: "⚠️ 无法连接到后端服务。请确认服务已启动。",
                    message_type: "text",
                });
            }
        };

        const approveTask = async () => {
            if (!currentTask.value) return;
            try {
                await fetch(`${API_BASE}/api/tasks/${currentTask.value.id}/approve`, { method: "POST" });
                currentTask.value.status = "in_progress";
            } catch (e) { console.error(e); }
        };

        const rejectTask = async () => {
            if (!currentTask.value) return;
            try {
                await fetch(`${API_BASE}/api/tasks/${currentTask.value.id}/reject`, { method: "POST" });
                currentTask.value.status = "failed";
            } catch (e) { console.error(e); }
        };

        const stopTask = async () => {
            if (!currentTask.value || !canStopTask.value) return;
            try {
                await fetch(`${API_BASE}/api/tasks/${currentTask.value.id}/stop`, { method: "POST" });
                currentTask.value.status = "stopped";
            } catch (e) {
                console.error(e);
                appendMessage({
                    id: "stop_err_" + Date.now(),
                    sender_id: "system",
                    content: "⚠️ 停止任务失败，请确认后端服务已启动。",
                    message_type: "text",
                });
            }
        };

        // --- Artifact ---
        const openArtifact = async (metadata) => {
            if (!metadata || !metadata.filename) return;

            modalTitle.value = metadata.filename;
            modalPath.value = metadata.folder || "";
            modalRawContent.value = "加载中...";
            isHtmlPreview.value = false;
            previewUrl.value = "";
            showModal.value = true;

            try {
                const folder = metadata.folder || "";
                const parts = folder.replace(/\\/g, "/").split("/");
                const taskFolder = parts[parts.length - 1] || "";
                const filePath = `${taskFolder}/${metadata.filename}`;

                // HTML 文件用 iframe 预览
                if (metadata.type === "html" || metadata.filename.endsWith(".html")) {
                    isHtmlPreview.value = true;
                    previewUrl.value = `${API_BASE}/api/workspace/preview/${filePath}`;
                    // 同时加载源码用于复制
                    const res = await fetch(`${API_BASE}/api/workspace/read/${filePath}`);
                    if (res.ok) {
                        const data = await res.json();
                        modalRawContent.value = data.content;
                    }
                } else {
                    // Markdown / 文本文件
                    const res = await fetch(`${API_BASE}/api/workspace/read/${filePath}`);
                    if (res.ok) {
                        const data = await res.json();
                        modalRawContent.value = data.content;
                    } else {
                        modalRawContent.value = `无法加载文件: ${metadata.filename}`;
                    }
                }
            } catch (e) {
                modalRawContent.value = `加载失败: ${e.message}`;
            }
        };

        const copyArtifact = async () => {
            try {
                await navigator.clipboard.writeText(modalRawContent.value);
                // Simple feedback
                const btn = document.querySelector('.modal-footer .btn-primary');
                if (btn) {
                    const original = btn.innerHTML;
                    btn.innerHTML = '<i class="fas fa-check"></i> 已复制';
                    setTimeout(() => { btn.innerHTML = original; }, 1500);
                }
            } catch (e) {
                console.error("Copy failed:", e);
            }
        };

        // --- History ---
        const loadHistoryList = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/history`);
                if (res.ok) historyList.value = await res.json();
            } catch (e) { console.error('Failed to load history:', e); }
        };

        const openHistory = async (conv) => {
            try {
                const res = await fetch(`${API_BASE}/api/history/${conv.id}`);
                if (!res.ok) return;
                const data = await res.json();
                // 加载历史消息到聊天面板，可继续对话
                messages.value = data.messages || [];
                const tasks = data.tasks || {};
                const taskIds = Object.keys(tasks);
                currentTask.value = tasks[taskIds[taskIds.length - 1]] || null;
                viewingHistory.value = true;
                viewingHistoryTitle.value = conv.title || '历史对话';
                showHistory.value = false;
                scrollToBottom();
            } catch (e) { console.error('Failed to load history:', e); }
        };

        const exitHistory = () => {
            // 退出历史对话，回到当前实时状态
            viewingHistory.value = false;
            viewingHistoryTitle.value = '';
            // 重新获取当前实时状态
            fetch(`${API_BASE}/api/system/state`)
                .then(r => r.json())
                .then(d => {
                    messages.value = [];
                    handleEvent({ type: 'state_update', data: d });
                })
                .catch(() => {});
        };

        const deleteHistory = async (conv, event) => {
            if (event && event.stopPropagation) event.stopPropagation();
            if (!confirm(`确定删除「${conv.title}」的历史记录？`)) return;
            try {
                await fetch(`${API_BASE}/api/history/${conv.id}`, { method: 'DELETE' });
                historyList.value = historyList.value.filter(h => h.id !== conv.id);
            } catch (e) { console.error(e); }
        };

        const newConversation = async () => {
            try {
                await fetch(`${API_BASE}/api/conversation/new`, { method: 'POST' });
                messages.value = [];
                currentTask.value = null;
                viewingHistory.value = false;
                viewingHistoryTitle.value = '';
                showHistory.value = false;
                await loadHistoryList();
            } catch (e) { console.error(e); }
        };

        const backToLive = () => {
            viewingHistory.value = false;
            viewingHistoryTitle.value = '';
            showHistory.value = false;
            // Re-fetch current state
            fetch(`${API_BASE}/api/system/state`)
                .then(r => r.json())
                .then(d => {
                    messages.value = [];
                    handleEvent({ type: 'state_update', data: d });
                })
                .catch(() => {});
        };

        const toggleHistory = async () => {
            showHistory.value = !showHistory.value;
            if (showHistory.value) await loadHistoryList();
        };

        const formatDate = (isoStr) => {
            if (!isoStr) return '';
            try {
                const d = new Date(isoStr);
                const now = new Date();
                const diff = now - d;
                if (diff < 86400000) {
                    return `今天 ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
                } else if (diff < 172800000) {
                    return `昨天 ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
                }
                return `${d.getMonth()+1}月${d.getDate()}日 ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
            } catch { return isoStr; }
        };

        // --- Scroll ---
        const isChatNearBottom = () => {
            const el = document.getElementById("chat-container");
            if (!el) return true;
            const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
            return distance < 96;
        };

        const scrollToBottom = () => {
            nextTick(() => {
                const el = document.getElementById("chat-container");
                if (el) el.scrollTop = el.scrollHeight;
            });
        };

        const scrollToBottomIfNeeded = (shouldScroll) => {
            if (shouldScroll) scrollToBottom();
        };

        const appendMessage = (message, options = {}) => {
            const shouldFollow = options.forceScroll || isChatNearBottom();
            messages.value.push(message);
            scrollToBottomIfNeeded(shouldFollow);
        };

        // --- Init ---
        onMounted(() => {
            // Show app after Vue mounts
            document.getElementById("app").style.display = "flex";

            connectWebSocket();

            // ─── Initialize Pixel Office ───────────────────────────────────────
            // Use nextTick + rAF to ensure layout is fully computed after display:flex
            nextTick(() => {
                requestAnimationFrame(() => {
                    const wrap = document.querySelector('.pixel-office-wrap');
                    const canvas = document.getElementById('pixel-office-canvas');
                    if (canvas && wrap) {
                        const setSize = () => {
                            const r = wrap.getBoundingClientRect();
                            console.log('[PixelOffice] Wrap size:', r.width, 'x', r.height);
                            if (r.width > 10 && r.height > 10) {
                                canvas.width = Math.floor(r.width);
                                canvas.height = Math.floor(r.height);
                            }
                        };
                        setSize();
                        window.pixelOffice = new PixelOffice(canvas);

                        // Resize canvas when panel resizes
                        const ro = new ResizeObserver(() => {
                            const r = wrap.getBoundingClientRect();
                            if (r.width > 10 && r.height > 10 && window.pixelOffice) {
                                window.pixelOffice.resize(r.width, r.height);
                            }
                        });
                        ro.observe(wrap);
                    } else {
                        console.warn('[PixelOffice] Canvas or wrap not found');
                    }
                });
            });

            // Initial state fetch
            fetch(`${API_BASE}/api/system/state`)
                .then((r) => r.json())
                .then((d) => handleEvent({ type: "state_update", data: d }))
                .catch(() => {});

            fetch(`${API_BASE}/api/office/registry`)
                .then((r) => r.json())
                .then((d) => {
                    officeRegistry.value = d || { agents: {}, workflow_map: [] };
                })
                .catch(() => {});
        });

        return {
            agents, messages, inputMessage, inputEl, currentTask, officeRegistry,
            mentionOpen, mentionCandidates, mentionIndex, handleInputChange, handleInputKeydown, selectMention,
            showAgentProfile, learningInProgress, lastLearningRoute,
            showModal, modalTitle, modalPath, modalRenderedContent, modalRawContent,
            isHtmlPreview, previewUrl,
            stages, currentStage, isStageComplete, canStopTask,
            showHistory, historyList, viewingHistory, viewingHistoryTitle, groupedHistory,
            officeAgents, selectedAgent, selectedAgentId, selectAgent, hideAgentProfile, getCapability, getWorkflowOwner,
            sendMessage, approveTask, rejectTask, stopTask,
            getStatusText, getAvatar, getAgentName, getAction, getCardClass,
            renderMarkdown, isOperationalMessage, friendlyMessage, isMessageExpanded, toggleMessageDetails,
            openArtifact, copyArtifact,
            toggleHistory, openHistory, deleteHistory, newConversation, backToLive, exitHistory, formatDate,
        };
    },
}).mount("#app");
