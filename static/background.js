const canvas = document.getElementById('stars-canvas');
const ctx = canvas.getContext('2d', { alpha: false }); // Disable alpha for better performance
let width, height, cx, cy;

function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
    cx = width / 2;
    cy = height / 2;
}
window.addEventListener('resize', resize);
resize();

// ---------------------------------------------------
// CONFIGURATION & THEME
// ---------------------------------------------------
const NEON_GREEN = '#00ffcc';
const NEON_GREEN_RGB = '0, 255, 204';
const BG_COLOR = '#050a10'; // Deep cyber-space black/blue

// ---------------------------------------------------
// 1. WARP SPEED STARS (Hyperdrive)
// ---------------------------------------------------
let stars = [];
const STAR_COUNT = 800;
let isWarping = false;
let warpFactor = 0; // Smooth transition 0 to 1

for (let i = 0; i < STAR_COUNT; i++) {
    stars.push({
        x: (Math.random() - 0.5) * 2000,
        y: (Math.random() - 0.5) * 2000,
        z: Math.random() * 2000,
        pz: Math.random() * 2000
    });
}

function updateAndDrawStars() {
    // Smooth easing for warp transition
    const targetWarp = isWarping ? 1 : 0;
    warpFactor += (targetWarp - warpFactor) * 0.05;
    
    const baseSpeed = 0.5;
    const warpSpeed = 40;
    const speed = baseSpeed + warpFactor * warpSpeed;

    ctx.fillStyle = `rgba(255, 255, 255, ${0.5 + warpFactor * 0.5})`;
    ctx.strokeStyle = `rgba(255, 255, 255, ${0.4 + warpFactor * 0.6})`;
    
    const fov = width;
    
    for (let star of stars) {
        star.pz = star.z;
        star.z -= speed;
        
        if (star.z <= 0) {
            star.z = 2000;
            star.pz = 2000;
            star.x = (Math.random() - 0.5) * 2000;
            star.y = (Math.random() - 0.5) * 2000;
        }
        
        let x = (star.x / star.z) * fov + cx;
        let y = (star.y / star.z) * fov + cy;
        let px = (star.x / star.pz) * fov + cx;
        let py = (star.y / star.pz) * fov + cy;
        
        let size = Math.max(0.1, (2000 - star.z) / 1000);
        
        if (warpFactor > 0.01) {
            // Draw lines for warp speed
            ctx.lineWidth = size * (1 + warpFactor);
            ctx.beginPath();
            ctx.moveTo(px, py);
            ctx.lineTo(x, y);
            ctx.stroke();
        } else {
            // Draw dots for normal drift
            ctx.fillRect(x, y, size * 1.5, size * 1.5);
        }
    }
}

// ---------------------------------------------------
// 2. MATRIX METEOR SHOWERS (Data Streams)
// ---------------------------------------------------
let meteors = [];
function updateAndDrawMeteors() {
    if (Math.random() < 0.08) {
        meteors.push({
            x: Math.random() * width,
            y: -200,
            length: 80 + Math.random() * 200,
            speed: 15 + Math.random() * 25,
            thickness: 1 + Math.random() * 2,
            opacity: 0.2 + Math.random() * 0.8
        });
    }
    
    for (let i = meteors.length - 1; i >= 0; i--) {
        let m = meteors[i];
        m.y += m.speed + (warpFactor * 20); // Faster during warp
        
        if (m.y - m.length > height) {
            meteors.splice(i, 1);
            continue;
        }
        
        let grad = ctx.createLinearGradient(m.x, m.y - m.length, m.x, m.y);
        grad.addColorStop(0, `rgba(${NEON_GREEN_RGB}, 0)`);
        grad.addColorStop(1, `rgba(${NEON_GREEN_RGB}, ${m.opacity})`);
        
        ctx.strokeStyle = grad;
        ctx.lineWidth = m.thickness;
        ctx.beginPath();
        ctx.moveTo(m.x, m.y - m.length);
        ctx.lineTo(m.x, m.y);
        ctx.stroke();
        
        // Data packet head
        ctx.fillStyle = '#fff';
        ctx.fillRect(m.x - m.thickness/2, m.y - 2, m.thickness, 4);
    }
}

// ---------------------------------------------------
// 3. NETWORK RADAR SWEEPS
// ---------------------------------------------------
let radarRadius = 0;
function drawRadar() {
    let radarMax = Math.max(width, height) * 1.2;
    radarRadius += 2 + (warpFactor * 5); // Sweeps faster during warp
    if (radarRadius > radarMax) radarRadius = 0;
    
    let opacity = Math.max(0, 1 - (radarRadius / radarMax));
    
    ctx.beginPath();
    ctx.arc(cx, cy, radarRadius, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${NEON_GREEN_RGB}, ${opacity * 0.15})`;
    ctx.lineWidth = 1;
    ctx.stroke();
    
    // Inner thick pulse
    ctx.beginPath();
    ctx.arc(cx, cy, radarRadius * 0.95, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${NEON_GREEN_RGB}, ${opacity * 0.05})`;
    ctx.lineWidth = 15;
    ctx.stroke();
}

// ---------------------------------------------------
// 4. HOLOGRAPHIC GLITCH PLANETS
// ---------------------------------------------------
const planetImgs = [];
for (let i = 0; i <= 3; i++) {
    const img = new Image();
    img.src = `/static/images/planets/planet_${i}.png`;
    planetImgs.push(img);
}

let activePlanets = [
    { imgIdx: 0, x: width * 0.85, y: height * 0.25, size: 400, phase: Math.random() * Math.PI * 2, glitching: false, glitchTimer: 0 },
    { imgIdx: 2, x: width * 0.15, y: height * 0.75, size: 250, phase: Math.random() * Math.PI * 2, glitching: false, glitchTimer: 0 },
    { imgIdx: 1, x: width * 0.5, y: height * 0.9, size: 600, phase: Math.random() * Math.PI * 2, glitching: false, glitchTimer: 0 }
];

function updateAndDrawPlanets() {
    for (let p of activePlanets) {
        // Floating animation
        const currentY = p.y + Math.sin(Date.now() * 0.0005 + p.phase) * 15;
        
        // Recalculate positions on resize to keep them responsive
        if (p.imgIdx === 0) p.x = width * 0.85;
        if (p.imgIdx === 2) p.x = width * 0.15;
        if (p.imgIdx === 1) p.x = width * 0.5;

        // Random cyber glitch trigger
        if (!p.glitching && Math.random() < 0.002) { 
            p.glitching = true;
            p.glitchTimer = 5 + Math.random() * 15; // Glitch duration in frames
        }
        
        if (p.glitching) {
            p.glitchTimer--;
            if (p.glitchTimer <= 0) p.glitching = false;
        }

        const img = planetImgs[p.imgIdx];
        if (!img.complete || img.naturalWidth === 0) continue;
        
        ctx.save();
        
        // Hologram opacity and blending mode
        ctx.globalAlpha = 0.5 - (warpFactor * 0.3); // Fade out slightly during warp
        ctx.globalCompositeOperation = 'screen';
        
        if (p.glitching) {
            // RGB Split Effect
            ctx.globalAlpha = 0.4;
            ctx.drawImage(img, p.x - p.size/2 - 10, currentY - p.size/2, p.size, p.size); // Red shift (simulated by compositing with original color)
            
            ctx.globalAlpha = 0.5;
            ctx.drawImage(img, p.x - p.size/2 + 10, currentY - p.size/2, p.size, p.size); // Cyan shift
            
            // Horizontal Slicing Glitch
            ctx.globalAlpha = 0.7;
            const sliceY = currentY - p.size/2 + Math.random() * p.size;
            const sliceH = 10 + Math.random() * 40;
            const offset = (Math.random() - 0.5) * 50;
            
            // Avoid drawing out of bounds of the source image
            const sy = Math.max(0, (sliceY - (currentY - p.size/2)) * (img.naturalHeight/p.size));
            const sh = Math.min(img.naturalHeight - sy, sliceH * (img.naturalHeight/p.size));
            
            if (sh > 0) {
                ctx.drawImage(img, 
                    0, sy, img.naturalWidth, sh,
                    p.x - p.size/2 + offset, sliceY, p.size, sliceH
                );
            }
        } else {
            // Normal Holographic Render
            ctx.drawImage(img, p.x - p.size/2, currentY - p.size/2, p.size, p.size);
        }
        
        // Cyan color wash over planet to enforce "Cyber" aesthetic
        ctx.globalCompositeOperation = 'source-atop';
        ctx.fillStyle = `rgba(${NEON_GREEN_RGB}, 0.1)`;
        ctx.fillRect(p.x - p.size/2, currentY - p.size/2, p.size, p.size);
        
        ctx.restore();
    }
}

// ---------------------------------------------------
// 5. POST-PROCESSING OVERLAYS
// ---------------------------------------------------
function drawOverlays() {
    // Deep Space Vignette
    const grad = ctx.createRadialGradient(cx, cy, height * 0.2, cx, cy, Math.max(width, height));
    grad.addColorStop(0, 'rgba(5, 10, 16, 0)');
    grad.addColorStop(1, 'rgba(2, 4, 8, 0.95)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);
    
    // Subtle CRT Scanlines
    ctx.fillStyle = `rgba(${NEON_GREEN_RGB}, 0.015)`;
    for (let i = 0; i < height; i += 4) {
        ctx.fillRect(0, i, width, 1);
    }
    
    // Screen noise/grain
    ctx.fillStyle = 'rgba(255, 255, 255, 0.01)';
    for(let i = 0; i < 500; i++) {
        ctx.fillRect(Math.random() * width, Math.random() * height, 1.5, 1.5);
    }
}

// ---------------------------------------------------
// MAIN RENDER LOOP (Highly Optimized)
// ---------------------------------------------------
function animate() {
    // Clear with opaque color to avoid alpha compositing overhead
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, width, height);
    
    // 1. Stars (Hyperdrive)
    updateAndDrawStars();
    
    // 2. Network Radar Sweeps
    drawRadar();
    
    // 3. Holographic Planets
    updateAndDrawPlanets();
    
    // 4. Matrix Data Streams
    updateAndDrawMeteors();
    
    // 5. Vignette & CRT overlays
    drawOverlays();
    
    requestAnimationFrame(animate);
}

// Start the engine
animate();

// ---------------------------------------------------
// INTERACTIVITY LISTENERS (Warp Speed)
// ---------------------------------------------------
window.addEventListener('mousedown', () => isWarping = true);
window.addEventListener('mouseup', () => isWarping = false);
window.addEventListener('touchstart', () => isWarping = true);
window.addEventListener('touchend', () => isWarping = false);
