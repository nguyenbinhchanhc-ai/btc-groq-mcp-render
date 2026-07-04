// Global State Variables
let currentModel = localStorage.getItem('groq-model') || 'llama-3.3-70b-versatile';
let currentTimeframe = '1h';
let isAnalyzing = false;
let lastFetchedPrice = 0;
let countdownSeconds = 30;
let countdownInterval = null;

// DOM Elements
const elements = {
    runBtn: document.getElementById('run-analysis'),
    settingsBtn: document.getElementById('open-settings'),
    closeSettingsBtns: document.querySelectorAll('#close-settings, #cancel-settings'),
    saveSettingsBtn: document.getElementById('save-settings'),
    settingsModal: document.getElementById('settings-modal'),
    groqApiKeyInput: document.getElementById('groq-api-key'),
    groqModelSelect: document.getElementById('groq-model'),
    apiStatus: document.getElementById('api-status'),
    activeModelLabel: document.getElementById('active-model'),
    
    // States
    emptyState: document.getElementById('analysis-empty'),
    loadingState: document.getElementById('analysis-loading'),
    loadingStep: document.getElementById('loading-step'),
    resultsState: document.getElementById('analysis-results'),
    
    // Live Price Display
    livePrice: document.getElementById('live-price'),
    priceChange: document.getElementById('price-change'),
    marketExchange: document.getElementById('market-exchange'),
    stat52wHigh: document.getElementById('stat-52w-high'),
    stat52wLow: document.getElementById('stat-52w-low'),
    statMarketState: document.getElementById('stat-market-state'),
    
    // S/R Levels
    nearRes: document.getElementById('near-res'),
    resDist: document.getElementById('res-dist'),
    nearSupp: document.getElementById('near-supp'),
    suppDist: document.getElementById('supp-dist'),
    srR3: document.getElementById('sr-r3'),
    srR2: document.getElementById('sr-r2'),
    srR1: document.getElementById('sr-r1'),
    srPv: document.getElementById('sr-pv'),
    srS1: document.getElementById('sr-s1'),
    srS2: document.getElementById('sr-s2'),
    srS3: document.getElementById('sr-s3'),

    // AI Results
    aiVerdict: document.getElementById('ai-verdict'),
    aiConfidence: document.getElementById('ai-confidence'),
    aiConfidenceFill: document.getElementById('ai-confidence-fill'),
    aiTargetPrice: document.getElementById('ai-target-price'),
    aiTargetTimeframe: document.getElementById('ai-target-timeframe'),
    bullishPct: document.getElementById('bullish-pct'),
    bearishPct: document.getElementById('bearish-pct'),
    probFillBull: document.getElementById('prob-fill-bull'),
    probFillBear: document.getElementById('prob-fill-bear'),
    aiJustification: document.getElementById('ai-justification'),
    bullishPoints: document.getElementById('bullish-points'),
    bearishPoints: document.getElementById('bearish-points'),
    
    // Indicators Table
    indicatorsTableBody: document.getElementById('indicators-table-body'),
    updateCountdown: document.getElementById('update-countdown'),

    // News
    newsContainer: document.getElementById('news-container'),
    
    // Toast
    toast: document.getElementById('toast'),
    toastMsg: document.getElementById('toast-message')
};

// Loading step text sequences in Vietnamese
const loadingSteps = [
    "Đang kết nối tới TradingView MCP...",
    "Truy vấn dữ liệu thời gian thực từ Binance...",
    "Lấy biến động giá và khối lượng từ Yahoo Finance...",
    "Đọc các đầu báo và tin tức crypto mới nhất...",
    "Tính toán tất cả các chỉ báo kỹ thuật liên quan...",
    "Đang phân tích và kiểm chứng chéo độ chính xác...",
    "Kích hoạt mô hình AI Groq tính toán xác suất & mục tiêu giá..."
];

// Translators for UI signals
const textMap = {
    'STRONG BUY': 'MUA MẠNH',
    'BUY': 'MUA',
    'HOLD': 'TRUNG LẬP',
    'SELL': 'BÁN',
    'STRONG SELL': 'BÁN MẠNH',
    
    'NEUTRAL': 'TRUNG LẬP',
    'BULLISH': 'TĂNG GIÁ',
    'BEARISH': 'GIẢM GIÁ',
    
    'Neutral': 'Trung lập',
    'Oversold': 'Quá bán',
    'Overbought': 'Quá mua',
    
    'Bullish': 'Tăng giá',
    'Bearish': 'Giảm giá',
    
    'Bullish Cross': 'Cắt lên Tăng giá',
    'Bearish Cross': 'Cắt xuống Giảm giá',
    
    'WEAK TREND': 'XU HƯỚNG YẾU',
    'STRONG TREND': 'XU HƯỚNG MẠNH',
    'Weak/No Trend': 'Xu hướng yếu',
    'Strong Trend': 'Xu hướng mạnh',
    'Moderate': 'Trung bình',
    
    'REGULAR': 'ĐANG HOẠT ĐỘNG',
    'CLOSED': 'ĐÓNG CỬA',
    
    'accumulation': 'Tích lũy',
    'distribution': 'Phân phối',
    
    'High': 'Biến động Cao',
    'Medium': 'Biến động Vừa',
    'Low': 'Biến động Thấp',
    
    'Normal': 'Bình thường',
    'Very High': 'Rất cao',
    'Very Low': 'Rất thấp',
    'Above Average': 'Trên trung bình',
    'Below Average': 'Dưới trung bình'
};

function translate(text) {
    if (!text) return '--';
    const cleanText = text.trim();
    return textMap[cleanText] || textMap[cleanText.toUpperCase()] || cleanText;
}

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    checkApiKeyStatus();
    setupEventListeners();
    
    // Initial fetch of price
    fetchQuoteOnly();
    
    // Wait 1.2 seconds and execute the first AI analysis automatically
    setTimeout(() => {
        runMarketAnalysis();
    }, 1200);
    
    // Polling 1: Price quote updates every 5 seconds
    setInterval(() => {
        fetchQuoteOnly();
    }, 5000);
    
    // Polling 2: Automatic loop to recalculate AI probabilities and targets every 30 seconds
    startAILoopTimer();
});

// Setup Event Listeners
function setupEventListeners() {
    // Timeframe selector buttons
    document.querySelectorAll('.tf-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            if (isAnalyzing) return;
            document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentTimeframe = e.target.getAttribute('data-tf');
            
            const tfNames = { '15m': '15 phút', '1h': '1 giờ', '4h': '4 giờ', '1D': '1 ngày' };
            showToast(`Khung thời gian chuyển sang ${tfNames[currentTimeframe]}`);
            
            // Re-fetch indicators and probabilities instantly on timeframe change
            runMarketAnalysis();
            resetAILoopTimer();
        });
    });

    // Run analysis button (Manual override)
    elements.runBtn.addEventListener('click', () => {
        runMarketAnalysis();
        resetAILoopTimer();
    });

    // Settings modal open
    elements.settingsBtn.addEventListener('click', () => {
        const savedKey = localStorage.getItem('groq-api-key') || '';
        elements.groqApiKeyInput.value = savedKey;
        elements.groqModelSelect.value = currentModel;
        elements.settingsModal.classList.remove('hidden');
    });

    // Settings modal close
    elements.closeSettingsBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            elements.settingsModal.classList.add('hidden');
        });
    });

    // Save Settings
    elements.saveSettingsBtn.addEventListener('click', () => {
        const key = elements.groqApiKeyInput.value.trim();
        const model = elements.groqModelSelect.value;
        
        localStorage.setItem('groq-api-key', key);
        localStorage.setItem('groq-model', model);
        currentModel = model;
        elements.activeModelLabel.innerText = model;
        
        checkApiKeyStatus();
        elements.settingsModal.classList.add('hidden');
        showToast('Đã lưu cấu hình thành công!');
        
        // Trigger run instantly with new API key
        runMarketAnalysis();
        resetAILoopTimer();
    });
}

// Load settings on startup
function loadSettings() {
    elements.activeModelLabel.innerText = currentModel;
}

// Check and update UI for API key status
function checkApiKeyStatus() {
    const key = localStorage.getItem('groq-api-key');
    const indicator = elements.apiStatus.querySelector('.status-indicator');
    const label = elements.apiStatus.querySelector('.status-label');
    
    if (key && key.startsWith('gsk_')) {
        indicator.className = 'status-indicator green';
        label.innerText = 'Groq API Key Sẵn Sàng';
    } else {
        indicator.className = 'status-indicator yellow';
        label.innerText = 'Chưa có Khóa Groq (Cài đặt)';
    }
}

// Helper to show a brief toast notification
function showToast(message) {
    elements.toastMsg.innerText = message;
    elements.toast.classList.remove('hidden');
    setTimeout(() => {
        elements.toast.classList.add('hidden');
    }, 3000);
}

// Polling Timer for Auto-Calculation
function startAILoopTimer() {
    countdownSeconds = 30;
    elements.updateCountdown.innerText = `Tự động cập nhật sau: ${countdownSeconds}s`;
    
    if (countdownInterval) clearInterval(countdownInterval);
    countdownInterval = setInterval(() => {
        countdownSeconds--;
        if (countdownSeconds <= 0) {
            countdownSeconds = 30;
            runMarketAnalysis(); // Triggers full AI analysis automatically!
        }
        elements.updateCountdown.innerText = `Tự động cập nhật sau: ${countdownSeconds}s`;
    }, 1000);
}

function resetAILoopTimer() {
    startAILoopTimer();
}

// Fetch live price quote only
async function fetchQuoteOnly() {
    try {
        const response = await fetch('/api/quote?symbol=BTC-USD');
        const data = await response.json();
        if (data && !data.error) {
            updatePriceUI(data);
        }
    } catch (e) {
        console.error('Failed to poll quote', e);
    }
}

// Update Price display area with change flash effect
function updatePriceUI(data) {
    if (!data || data.error) return;
    
    const oldPrice = lastFetchedPrice;
    const newPrice = data.price;
    lastFetchedPrice = newPrice;
    
    const formattedPrice = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(newPrice);
    elements.livePrice.innerText = formattedPrice;
    
    // Pulse animation when price changes
    if (oldPrice > 0 && oldPrice !== newPrice) {
        const pulseClass = newPrice > oldPrice ? 'price-up-pulse' : 'price-down-pulse';
        elements.livePrice.classList.add(pulseClass);
        setTimeout(() => {
            elements.livePrice.classList.remove(pulseClass);
        }, 800);
    }
    
    const chgSign = data.change >= 0 ? '+' : '';
    const chgPct = data.change_pct;
    const formattedChg = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(data.change));
    
    elements.priceChange.className = data.change >= 0 ? 'price-change positive' : 'price-change negative';
    elements.priceChange.innerHTML = `<i class="fa-solid ${data.change >= 0 ? 'fa-caret-up' : 'fa-caret-down'}"></i> ${chgSign}${chgPct}% (${chgSign}${formattedChg})`;
    
    if (data['52w_high']) {
        elements.stat52wHigh.innerText = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(data['52w_high']);
    }
    if (data['52w_low']) {
        elements.stat52wLow.innerText = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(data['52w_low']);
    }
    
    const mktState = data.market_state || 'REGULAR';
    elements.statMarketState.innerText = translate(mktState);
    elements.statMarketState.className = mktState === 'REGULAR' ? 'stat-val state-active' : 'stat-val state-closed';
}

// Render Support & Resistance levels panel
function renderSupportResistance(sr) {
    if (!sr) return;
    
    elements.nearRes.innerText = sr.nearest_resistance ? `$${Math.round(sr.nearest_resistance).toLocaleString()}` : '--';
    elements.resDist.innerText = sr.distance_to_resistance_pct ? `+${sr.distance_to_resistance_pct}%` : '--';
    elements.nearSupp.innerText = sr.nearest_support ? `$${Math.round(sr.nearest_support).toLocaleString()}` : '--';
    elements.suppDist.innerText = sr.distance_to_support_pct ? `-${sr.distance_to_support_pct}%` : '--';
    
    elements.srR3.innerText = sr.resistance_3 ? `$${Math.round(sr.resistance_3).toLocaleString()}` : '--';
    elements.srR2.innerText = sr.resistance_2 ? `$${Math.round(sr.resistance_2).toLocaleString()}` : '--';
    elements.srR1.innerText = sr.resistance_1 ? `$${Math.round(sr.resistance_1).toLocaleString()}` : '--';
    elements.srPv.innerText = sr.pivot ? `$${Math.round(sr.pivot).toLocaleString()}` : '--';
    elements.srS1.innerText = sr.support_1 ? `$${Math.round(sr.support_1).toLocaleString()}` : '--';
    elements.srS2.innerText = sr.support_2 ? `$${Math.round(sr.support_2).toLocaleString()}` : '--';
    elements.srS3.innerText = sr.support_3 ? `$${Math.round(sr.support_3).toLocaleString()}` : '--';
}

// Render the comprehensive technical indicators table rows
function renderIndicatorsTable(tv) {
    if (!tv) return;
    
    elements.indicatorsTableBody.innerHTML = '';
    
    const price = tv.price_data.current_price;
    const rsi = tv.rsi || {};
    const macd = tv.macd || {};
    const stoch = tv.stochastic || {};
    const stochRsi = tv.stochastic_rsi || {};
    const adx = tv.adx || {};
    const bb = tv.bollinger_bands || {};
    const atr = tv.atr || {};
    const vol = tv.volume_analysis || {};
    const sma = tv.sma || {};
    const ema = tv.ema || {};
    const cci = tv.cci || {};
    const wr = tv.williams_r || {};
    const ao = tv.awesome_oscillator || {};
    const mom = tv.momentum || {};

    const indicatorsData = [
        {
            group: 'Động lượng',
            name: 'RSI (14)',
            val: rsi.value !== undefined ? rsi.value.toFixed(2) : '--',
            sig: translate(rsi.signal),
            desc: rsi.value > 70 ? 'Thị trường quá mua, cảnh báo điều chỉnh' : rsi.value < 30 ? 'Thị trường quá bán, cơ hội hồi phục' : 'Động lượng RSI di chuyển trung tính'
        },
        {
            group: 'Động lượng',
            name: 'MACD (12, 26, 9)',
            val: `M: ${(macd.macd_line || 0).toFixed(2)} | S: ${(macd.signal_line || 0).toFixed(2)}`,
            sig: translate(macd.crossover),
            desc: macd.crossover === 'Bullish' ? 'Đường MACD cắt lên trên đường tín hiệu (Tăng)' : 'Đường MACD cắt xuống dưới đường tín hiệu (Giảm)'
        },
        {
            group: 'Động lượng',
            name: 'Stochastic Oscillator',
            val: `%K: ${(stoch.k || 0).toFixed(2)} | %D: ${(stoch.d || 0).toFixed(2)}`,
            sig: translate(stoch.signal),
            desc: stoch.signal === 'Oversold' ? 'Stoch chạm vùng quá bán' : stoch.signal === 'Overbought' ? 'Stoch chạm vùng quá mua' : 'Dao động Stoch ở vùng trung hòa'
        },
        {
            group: 'Động lượng',
            name: 'Stochastic RSI',
            val: `%K: ${(stochRsi.k || 0).toFixed(2)}`,
            sig: translate(stochRsi.signal),
            desc: 'Kết hợp RSI và Stochastic xác định động lượng đảo chiều cực nhạy'
        },
        {
            group: 'Động lượng',
            name: 'Awesome Oscillator (AO)',
            val: (ao.value || 0).toFixed(2),
            sig: translate(ao.signal),
            desc: ao.signal.includes('Bullish') ? 'Động lượng AO chuyển sang dương' : 'Động lượng AO chuyển sang âm'
        },
        {
            group: 'Động lượng',
            name: 'Momentum (MOM)',
            val: (mom.value || 0).toFixed(2),
            sig: translate(mom.signal),
            desc: mom.signal.includes('Bullish') ? 'Tốc độ tăng giá đang gia tăng' : 'Tốc độ giảm giá đang gia tăng'
        },
        {
            group: 'Động lượng',
            name: 'Williams %R',
            val: (wr.value || 0).toFixed(2),
            sig: translate(wr.signal),
            desc: 'Đo lường mức độ quá mua/quá bán từ đỉnh/đáy lịch sử'
        },
        {
            group: 'Xu hướng',
            name: 'Chỉ số ADX (14)',
            val: (adx.value || 0).toFixed(2),
            sig: translate(adx.trend_strength),
            desc: `Độ mạnh xu hướng: ${translate(adx.trend_strength)}. (+DI: ${adx.plus_di || 0} | -DI: ${adx.minus_di || 0})`
        },
        {
            group: 'Xu hướng',
            name: 'Đường EMA (20) Ngắn',
            val: Math.round(ema.ema20 || 0).toLocaleString(),
            sig: price > (ema.ema20 || 0) ? 'MUA' : 'BÁN',
            desc: price > (ema.ema20 || 0) ? 'Giá nằm trên EMA20 hỗ trợ ngắn hạn' : 'Giá nằm dưới EMA20 cản ngắn hạn'
        },
        {
            group: 'Xu hướng',
            name: 'Đường SMA (50) Vừa',
            val: Math.round(sma.sma50 || 0).toLocaleString(),
            sig: price > (sma.sma50 || 0) ? 'MUA' : 'BÁN',
            desc: price > (sma.sma50 || 0) ? 'Xu hướng trung hạn đang tăng' : 'Xu hướng trung hạn đang giảm'
        },
        {
            group: 'Xu hướng',
            name: 'Đường SMA (200) Dài',
            val: Math.round(sma.sma200 || 0).toLocaleString(),
            sig: price > (sma.sma200 || 0) ? 'MUA' : 'BÁN',
            desc: price > (sma.sma200 || 0) ? 'Xu hướng dài hạn tăng vững chắc (Thị trường Bò)' : 'Xu hướng dài hạn giảm (Thị trường Gấu)'
        },
        {
            group: 'Biến động',
            name: 'Dải Bollinger Bands (20,2)',
            val: `U: ${Math.round(bb.upper || 0).toLocaleString()} | L: ${Math.round(bb.lower || 0).toLocaleString()}`,
            sig: bb.squeeze ? 'NÉN (VOL THẤP)' : 'MỞ RỘNG',
            desc: `Giá nằm ở ${translate(bb.position)}. Độ rộng BBw: ${(bb.width || 0).toFixed(4)}`
        },
        {
            group: 'Biến động',
            name: 'Chỉ báo ATR (14)',
            val: `${(atr.value || 0).toFixed(2)} (${(atr.percent_of_price || 0).toFixed(2)}%)`,
            sig: translate(atr.volatility),
            desc: `Biến động giá hiện tại ở mức ${translate(atr.volatility)}`
        },
        {
            group: 'Khối lượng',
            name: 'Khối lượng giao dịch (Vol)',
            val: Math.round(vol.current || 0).toLocaleString(),
            sig: translate(vol.signal),
            desc: `Vol hiện tại bằng ${vol.ratio || 0} lần Vol trung bình 20 ngày (${Math.round(vol.average_20 || 0).toLocaleString()})`
        }
    ];

    indicatorsData.forEach(ind => {
        const tr = document.createElement('tr');
        
        let sigClass = 'badge badge-neutral';
        if (ind.sig.includes('MUA') || ind.sig.includes('TĂNG') || ind.sig.includes('MỞ RỘNG') || ind.sig.includes('MẠNH')) {
            sigClass = 'badge badge-buy';
        } else if (ind.sig.includes('BÁN') || ind.sig.includes('GIẢM') || ind.sig.includes('NÉN') || ind.sig.includes('YẾU')) {
            sigClass = 'badge badge-sell';
        }

        tr.innerHTML = `
            <td>${ind.group}</td>
            <td>${ind.name}</td>
            <td>${ind.val}</td>
            <td><span class="${sigClass}">${ind.sig}</span></td>
            <td style="color: var(--text-secondary); font-size: 12px;">${ind.desc}</td>
        `;
        elements.indicatorsTableBody.appendChild(tr);
    });
}

// Run the full AI Analysis flow (fast Groq API request)
async function runMarketAnalysis() {
    if (isAnalyzing) return;
    
    isAnalyzing = true;
    elements.runBtn.disabled = true;
    elements.runBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang tính...`;
    
    // Only show loading spinner on the very first load
    const hasExistingResults = !elements.resultsState.classList.contains('hidden');
    if (!hasExistingResults) {
        elements.emptyState.classList.add('hidden');
        elements.loadingState.classList.remove('hidden');
    } else {
        elements.updateCountdown.innerText = "Đang phân tích lại...";
    }
    
    // Animate loading step texts
    let stepIdx = 0;
    elements.loadingStep.innerText = loadingSteps[0];
    const stepInterval = setInterval(() => {
        stepIdx = (stepIdx + 1) % loadingSteps.length;
        elements.loadingStep.innerText = loadingSteps[stepIdx];
    }, 2500);

    const apiKey = localStorage.getItem('groq-api-key') || '';
    
    try {
        const response = await fetch(`/api/analyze?symbol=BTCUSDT&exchange=BINANCE&timeframe=${currentTimeframe}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Groq-Api-Key': apiKey,
                'X-Groq-Model': currentModel
            }
        });
        
        clearInterval(stepInterval);
        const data = await response.json();
        
        if (response.ok && !data.error) {
            elements.loadingState.classList.add('hidden');
            elements.resultsState.classList.remove('hidden');
            
            // Render technical sections instantly with newest data
            renderSupportResistance(data.technical_details.support_resistance);
            renderIndicatorsTable(data.technical_details);
            
            // Render Groq AI results
            renderAIResults(data);
            showToast('Tính toán xác suất & mục tiêu thành công!');
        } else {
            throw new Error(data.error || 'Máy chủ trả về mã lỗi');
        }
    } catch (err) {
        clearInterval(stepInterval);
        console.error(err);
        
        // If first load failed, show empty state, otherwise keep old results and show error
        if (!hasExistingResults) {
            elements.loadingState.classList.add('hidden');
            elements.emptyState.classList.remove('hidden');
        }
        
        showToast(`Lỗi: ${err.message || 'Kiểm tra mạng / API key'}`);
    } finally {
        isAnalyzing = false;
        elements.runBtn.disabled = false;
        elements.runBtn.innerHTML = `<i class="fa-solid fa-bolt"></i> Chạy phân tích`;
    }
}

// Render dynamic AI results
function renderAIResults(data) {
    updatePriceUI(data.price_details);
    if (data.technical_details.exchange) {
        elements.marketExchange.innerText = data.technical_details.exchange;
    }
    
    const ai = data.ai_analysis;
    
    // 1. Verdict decision
    const verdict = ai.decision || 'HOLD';
    elements.aiVerdict.innerText = translate(verdict);
    elements.aiVerdict.className = 'recommendation-badge ' + 
        (verdict.includes('STRONG BUY') ? 'strong-buy' : 
         verdict.includes('BUY') ? 'buy' : 
         verdict.includes('STRONG SELL') ? 'strong-sell' : 
         verdict.includes('SELL') ? 'sell' : 'hold');
         
    const confidence = ai.confidence || 0;
    elements.aiConfidence.innerText = `${confidence}%`;
    elements.aiConfidenceFill.style.width = `${confidence}%`;
    
    // 2. Mathematical targets
    const targetVal = ai.target_price || 0;
    elements.aiTargetPrice.innerText = targetVal ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(targetVal) : '$ --,---.--';
    elements.aiTargetTimeframe.innerText = ai.target_timeframe || '--';
    
    // 3. Probabilities
    const bullPct = ai.probability_bullish || 50;
    const bearPct = ai.probability_bearish || 50;
    elements.bullishPct.innerText = `${bullPct}% TĂNG`;
    elements.bearishPct.innerText = `${bearPct}% GIẢM`;
    elements.probFillBull.style.width = `${bullPct}%`;
    elements.probFillBear.style.width = `${bearPct}%`;
    
    // 4. Justifications & points
    elements.aiJustification.innerText = ai.reasoning || ai.justification || 'Không có luận chứng tóm tắt.';
    
    elements.bullishPoints.innerHTML = '';
    const bullPoints = ai.bullish_thesis_points || ai.bullish_thesis || [];
    if (bullPoints.length === 0) {
        elements.bullishPoints.innerHTML = '<li>Không phát hiện luận điểm tăng giá cụ thể.</li>';
    } else {
        bullPoints.forEach(pt => {
            const li = document.createElement('li');
            li.innerText = pt;
            elements.bullishPoints.appendChild(li);
        });
    }
    
    elements.bearishPoints.innerHTML = '';
    const bearPoints = ai.bearish_thesis_points || ai.bearish_thesis || [];
    if (bearPoints.length === 0) {
        elements.bearishPoints.innerHTML = '<li>Không phát hiện luận điểm giảm giá cụ thể.</li>';
    } else {
        bearPoints.forEach(pt => {
            const li = document.createElement('li');
            li.innerText = pt;
            elements.bearishPoints.appendChild(li);
        });
    }
    
    // 5. Render News Headlines
    elements.newsContainer.innerHTML = '';
    const news = data.news_details || [];
    if (news.length === 0) {
        elements.newsContainer.innerHTML = `
            <div class="news-item">
                <span class="news-time">Không có tin tức</span>
                <span class="news-title">Không tìm thấy tin tức tiêu đề thị trường lúc này.</span>
            </div>
        `;
    } else {
        news.forEach(item => {
            const timeStr = item.time || 'Vừa xong';
            const title = item.title || 'Tiêu đề';
            const link = item.link || '#';
            const source = item.source || 'Tin Tài Chính';
            
            const itemDiv = document.createElement('div');
            itemDiv.className = 'news-item';
            itemDiv.innerHTML = `
                <span class="news-time">${timeStr}</span>
                <a href="${link}" target="_blank" class="news-title">${title}</a>
                <span class="news-source">${source}</span>
            `;
            elements.newsContainer.appendChild(itemDiv);
        });
    }
}
