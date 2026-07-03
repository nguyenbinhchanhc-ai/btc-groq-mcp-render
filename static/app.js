// Global State Variables
let currentModel = localStorage.getItem('groq-model') || 'llama-3.3-70b-versatile';
let currentTimeframe = '1h';
let isAnalyzing = false;

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
    
    // Gauges
    rsiVal: document.getElementById('rsi-val'),
    rsiValBar: document.getElementById('rsi-val-bar'),
    rsiStatus: document.getElementById('rsi-status'),
    macdLine: document.getElementById('macd-line'),
    macdSignal: document.getElementById('macd-signal'),
    macdCrossover: document.getElementById('macd-crossover'),
    bbUpper: document.getElementById('bb-upper'),
    bbLower: document.getElementById('bb-lower'),
    bbWidth: document.getElementById('bb-width'),
    bbPosition: document.getElementById('bb-position'),
    bbDescription: document.getElementById('bb-description'),
    
    // AI Results
    aiVerdict: document.getElementById('ai-verdict'),
    aiConfidence: document.getElementById('ai-confidence'),
    aiConfidenceFill: document.getElementById('ai-confidence-fill'),
    aiJustification: document.getElementById('ai-justification'),
    bullishPoints: document.getElementById('bullish-points'),
    bearishPoints: document.getElementById('bearish-points'),
    
    // Confluence
    tvSignal: document.getElementById('tv-signal'),
    indRsi: document.getElementById('ind-rsi'),
    indMacd: document.getElementById('ind-macd'),
    indStoch: document.getElementById('ind-stoch'),
    indAdx: document.getElementById('ind-adx'),
    indMa: document.getElementById('ind-ma'),
    
    // News
    newsContainer: document.getElementById('news-container'),
    
    // Toast
    toast: document.getElementById('toast'),
    toastMsg: document.getElementById('toast-message')
};

// Loading step text sequences
const loadingSteps = [
    "Connecting to TradingView MCP...",
    "Querying Binance real-time order books...",
    "Fetching Yahoo Finance historical volatility data...",
    "Retrieving live cryptocurrency financial headlines...",
    "Analyzing Technical Indicators (RSI, MACD, Bollinger Bands)...",
    "Running multi-agent analysis debate on Groq AI...",
    "Formulating consensus trading recommendation..."
];

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    checkApiKeyStatus();
    setupEventListeners();
    fetchQuoteOnly(); // Initial silent fetch of live price
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
            showToast(`Timeframe changed to ${currentTimeframe}`);
        });
    });

    // Run analysis button
    elements.runBtn.addEventListener('click', () => {
        runMarketAnalysis();
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
        showToast('Settings saved successfully!');
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
        label.innerText = 'Groq API Key Ready';
    } else {
        indicator.className = 'status-indicator yellow';
        label.innerText = 'Missing Groq Key (Set in Settings)';
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

// Fetch live price quote only (without full AI analysis)
async function fetchQuoteOnly() {
    try {
        const response = await fetch('/api/quote?symbol=BTC-USD');
        const data = await response.json();
        if (data && !data.error) {
            updatePriceUI(data);
        }
    } catch (e) {
        console.error('Failed to fetch initial quote', e);
    }
}

// Run the full AI Analysis flow
async function runMarketAnalysis() {
    if (isAnalyzing) return;
    
    isAnalyzing = true;
    elements.runBtn.disabled = true;
    elements.runBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...`;
    
    // Transition UI states
    elements.emptyState.classList.add('hidden');
    elements.resultsState.classList.add('hidden');
    elements.loadingState.classList.remove('hidden');
    
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
            renderAnalysisResults(data);
            showToast('Analysis completed!');
        } else {
            throw new Error(data.error || 'Server returned an error');
        }
    } catch (err) {
        clearInterval(stepInterval);
        console.error(err);
        elements.loadingState.classList.add('hidden');
        elements.emptyState.classList.remove('hidden');
        showToast(`Error: ${err.message || 'Check connection / API keys'}`);
    } finally {
        isAnalyzing = false;
        elements.runBtn.disabled = false;
        elements.runBtn.innerHTML = `<i class="fa-solid fa-bolt"></i> Run Analysis`;
    }
}

// Update Price display area
function updatePriceUI(data) {
    if (!data || data.error) return;
    
    const formattedPrice = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(data.price);
    elements.livePrice.innerText = formattedPrice;
    
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
    
    elements.statMarketState.innerText = data.market_state || 'REGULAR';
    elements.statMarketState.className = data.market_state === 'REGULAR' ? 'stat-val state-active' : 'stat-val state-closed';
}

// Render dynamic results
function renderAnalysisResults(data) {
    // 1. Update live price/market details
    updatePriceUI(data.price_details);
    if (data.technical_details.exchange) {
        elements.marketExchange.innerText = data.technical_details.exchange;
    }
    
    // 2. Render technical indicators (gauges)
    const tv = data.technical_details;
    
    // RSI
    if (tv.rsi && tv.rsi.rsi) {
        const rsi = parseFloat(tv.rsi.rsi);
        elements.rsiVal.innerText = rsi.toFixed(1);
        elements.rsiValBar.style.width = `${rsi}%`;
        
        let status = 'Neutral';
        let rsiClass = 'badge badge-neutral';
        if (rsi < 30) {
            status = 'Oversold';
            rsiClass = 'badge badge-buy';
        } else if (rsi > 70) {
            status = 'Overbought';
            rsiClass = 'badge badge-sell';
        }
        elements.rsiStatus.innerText = status;
        elements.rsiStatus.className = rsiClass;
        
        elements.indRsi.innerText = status.toUpperCase();
        elements.indRsi.className = rsiClass;
    }
    
    // MACD
    if (tv.macd) {
        const macd = tv.macd.macd || 0;
        const signal = tv.macd.signal || 0;
        elements.macdLine.innerText = macd.toFixed(2);
        elements.macdSignal.innerText = signal.toFixed(2);
        
        const isBullish = macd > signal;
        elements.macdCrossover.innerText = isBullish ? 'Bullish Cross' : 'Bearish Cross';
        elements.macdCrossover.className = isBullish ? 'macd-status bullish' : 'macd-status bearish';
        
        elements.indMacd.innerText = isBullish ? 'BULLISH' : 'BEARISH';
        elements.indMacd.className = isBullish ? 'badge badge-buy' : 'badge badge-sell';
    }
    
    // Bollinger Bands
    if (tv.bollinger_bands) {
        const bb = tv.bollinger_bands;
        elements.bbUpper.innerText = Math.round(bb.upper || 0).toLocaleString();
        elements.bbLower.innerText = Math.round(bb.lower || 0).toLocaleString();
        elements.bbWidth.innerText = (bb.width || 0).toFixed(4);
        
        // Calculate price position percentage inside bands
        const current = tv.price_data.current_price;
        const upper = bb.upper || current;
        const lower = bb.lower || current;
        let positionPct = 50;
        if (upper !== lower) {
            positionPct = ((current - lower) / (upper - lower)) * 100;
            positionPct = Math.max(0, Math.min(100, positionPct)); // clamp 0-100
        }
        elements.bbPosition.style.left = `${positionPct}%`;
        
        let bbDesc = 'Neutral Bands';
        if (bb.width < 0.02) bbDesc = 'Squeeze Alert (Low Vol)';
        else if (positionPct > 90) bbDesc = 'Price testing Upper Band';
        else if (positionPct < 10) bbDesc = 'Price testing Lower Band';
        elements.bbDescription.innerText = bbDesc;
    }
    
    // ADX
    if (tv.adx) {
        const adx = tv.adx.adx || 0;
        let adxText = 'WEAK TREND';
        let adxClass = 'badge badge-neutral';
        if (adx > 25) {
            adxText = 'STRONG TREND';
            adxClass = 'badge badge-buy';
        }
        elements.indAdx.innerText = `${adxText} (${Math.round(adx)})`;
        elements.indAdx.className = adxClass;
    }
    
    // Stochastic
    if (tv.stochastic) {
        const k = tv.stochastic.k || 50;
        let stochText = 'NEUTRAL';
        let stochClass = 'badge badge-neutral';
        if (k < 20) {
            stochText = 'OVERSOLD';
            stochClass = 'badge badge-buy';
        } else if (k > 80) {
            stochText = 'OVERBOUGHT';
            stochClass = 'badge badge-sell';
        }
        elements.indStoch.innerText = stochText;
        elements.indStoch.className = stochClass;
    }
    
    // MAs / EMA
    if (tv.market_sentiment) {
        const rating = tv.market_sentiment.overall_rating || 0;
        let ratingText = 'NEUTRAL';
        let ratingClass = 'badge badge-neutral';
        
        if (rating > 0.5) {
            ratingText = 'BULLISH';
            ratingClass = 'badge badge-buy';
        } else if (rating < -0.5) {
            ratingText = 'BEARISH';
            ratingClass = 'badge badge-sell';
        }
        elements.indMa.innerText = ratingText;
        elements.indMa.className = ratingClass;
        
        // Overall TV Signal
        const tvSigText = (tv.market_sentiment.buy_sell_signal || 'NEUTRAL').toUpperCase();
        elements.tvSignal.innerText = tvSigText;
        elements.tvSignal.className = 'confluence-val ' + 
            (tvSigText.includes('BUY') ? 'strong-buy' : tvSigText.includes('SELL') ? 'strong-sell' : 'neutral');
    }
    
    // 3. Render Groq AI Analysis
    const ai = data.ai_analysis;
    const verdict = (ai.decision || 'HOLD').toUpperCase();
    elements.aiVerdict.innerText = verdict;
    elements.aiVerdict.className = 'recommendation-badge ' + 
        (verdict.includes('STRONG BUY') ? 'strong-buy' : 
         verdict.includes('BUY') ? 'buy' : 
         verdict.includes('STRONG SELL') ? 'strong-sell' : 
         verdict.includes('SELL') ? 'sell' : 'hold');
         
    const confidence = ai.confidence || 0;
    elements.aiConfidence.innerText = `${confidence}%`;
    elements.aiConfidenceFill.style.width = `${confidence}%`;
    
    elements.aiJustification.innerText = ai.reasoning || ai.justification || 'No justification provided.';
    
    // Bullet points
    elements.bullishPoints.innerHTML = '';
    const bullPoints = ai.bullish_thesis_points || ai.bullish_thesis || [];
    if (bullPoints.length === 0) {
        elements.bullishPoints.innerHTML = '<li>No specific bullish points found.</li>';
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
        elements.bearishPoints.innerHTML = '<li>No specific bearish points found.</li>';
    } else {
        bearPoints.forEach(pt => {
            const li = document.createElement('li');
            li.innerText = pt;
            elements.bearishPoints.appendChild(li);
        });
    }
    
    // 4. Render News Headlines
    elements.newsContainer.innerHTML = '';
    const news = data.news_details || [];
    if (news.length === 0) {
        elements.newsContainer.innerHTML = `
            <div class="news-item">
                <span class="news-time">No news found</span>
                <span class="news-title">Could not fetch headlines for BTC at this time.</span>
            </div>
        `;
    } else {
        news.forEach(item => {
            const timeStr = item.time || 'Recent';
            const title = item.title || 'Headline';
            const link = item.link || '#';
            const source = item.source || 'Finance News';
            
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
