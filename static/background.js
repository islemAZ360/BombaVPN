document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('stars-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d', { alpha: false }); 

    let width, height, centerX, centerY;
    let nodes = [];
    let planets = [];
    let nebulas = [];
    let dataStreams = [];
    let radarRadius = 0;
    let lightningFlash = 0;
    
    // Parallax & Warp Speed controls
    let mouse = { screenX: -1000, screenY: -1000, targetX: 0, targetY: 0, currentX: 0, currentY: 0 };
    let isWarping = false;
    let warpSpeed = 1; // Base speed
    
    const colors = {
        bg: '#0a0e1a',
        neonGreen: 'rgba(0, 255, 204, 1)',
        neonGreenFaint: 'rgba(0, 255, 204, 0.1)',
        cyan: 'rgba(0, 204, 255, 0.3)',
        nebula1: 'rgba(0, 60, 80, 0.15)',
        nebula2: 'rgba(0, 255, 204, 0.05)'
    };

    function resize() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
        centerX = width / 2;
        centerY = height / 2;
        initElements();
    }

    window.addEventListener('resize', resize);
    
    // Mouse Interaction
    window.addEventListener('mousemove', (e) => {
        mouse.screenX = e.clientX;
        mouse.screenY = e.clientY;
        mouse.targetX = (e.clientX - centerX) * 0.5;
        mouse.targetY = (e.clientY - centerY) * 0.5;
    });

    window.addEventListener('mouseout', () => {
        mouse.screenX = -1000;
        mouse.screenY = -1000;
        mouse.targetX = 0;
        mouse.targetY = 0;
        isWarping = false;
    });

    // window.addEventListener('mousedown', () => isWarping = true);
    // window.addEventListener('mouseup', () => isWarping = false);

    // Touch Interaction
    window.addEventListener('touchmove', (e) => {
        if(e.touches.length > 0) {
            mouse.screenX = e.touches[0].clientX;
            mouse.screenY = e.touches[0].clientY;
            mouse.targetX = (e.touches[0].clientX - centerX) * 0.5;
            mouse.targetY = (e.touches[0].clientY - centerY) * 0.5;
        }
    }, { passive: true });

    // window.addEventListener('touchstart', () => isWarping = true, { passive: true });
    window.addEventListener('touchend', () => {
        mouse.screenX = -1000;
        mouse.screenY = -1000;
        mouse.targetX = 0;
        mouse.targetY = 0;
        isWarping = false;
    });

    class Node {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.z = Math.random() * 2 + 0.8; 
            this.vx = (Math.random() - 0.5) * 0.2;
            this.vy = (Math.random() - 0.5) * 0.2;
            this.radius = (Math.random() * 1.5 + 0.5) / this.z;
            this.baseAlpha = Math.random() * 0.5 + 0.2;
        }

        update() {
            // Apply warp speed multiplier
            this.x += (this.vx / this.z) * warpSpeed;
            this.y += (this.vy / this.z) * warpSpeed;

            // Warp effect: pull towards edges when fast
            if (warpSpeed > 2) {
                let dx = this.x - centerX;
                let dy = this.y - centerY;
                this.x += dx * 0.01 * warpSpeed;
                this.y += dy * 0.01 * warpSpeed;
            }

            if (this.x < -100) this.x = width + 100;
            if (this.x > width + 100) this.x = -100;
            if (this.y < -100) this.y = height + 100;
            if (this.y > height + 100) this.y = -100;
        }

        draw(px, py) {
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;

            ctx.fillStyle = `rgba(255, 255, 255, ${this.baseAlpha})`;
            ctx.beginPath();
            
            // Stretch nodes into lines during warp speed
            if (warpSpeed > 2) {
                let stretchX = (drawX - centerX) * 0.05 * warpSpeed;
                let stretchY = (drawY - centerY) * 0.05 * warpSpeed;
                ctx.moveTo(drawX, drawY);
                ctx.lineTo(drawX - stretchX, drawY - stretchY);
                ctx.strokeStyle = `rgba(0, 255, 204, ${this.baseAlpha})`;
                ctx.lineWidth = this.radius;
                ctx.stroke();
            } else {
                // Glowing synapses (Neural Network style)
                ctx.fillStyle = `rgba(0, 255, 204, ${this.baseAlpha * 0.4})`;
                ctx.beginPath();
                ctx.arc(drawX, drawY, this.radius * 3.5, 0, Math.PI * 2);
                ctx.fill();

                ctx.fillStyle = `rgba(255, 255, 255, ${this.baseAlpha})`;
                ctx.beginPath();
                ctx.arc(drawX, drawY, this.radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    class Nebula {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.radius = Math.random() * 600 + 300;
            this.vx = (Math.random() - 0.5) * 0.05;
            this.vy = (Math.random() - 0.5) * 0.05;
            this.z = 5;
            this.color = Math.random() > 0.5 ? colors.nebula1 : colors.nebula2;
        }
        update() {
            this.x += this.vx * (warpSpeed * 0.2);
            this.y += this.vy * (warpSpeed * 0.2);
            if (this.x < -this.radius) this.x = width + this.radius;
            if (this.x > width + this.radius) this.x = -this.radius;
            if (this.y < -this.radius) this.y = height + this.radius;
            if (this.y > height + this.radius) this.y = -this.radius;
        }
        draw(px, py) {
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;
            let grad = ctx.createRadialGradient(drawX, drawY, 0, drawX, drawY, this.radius);
            grad.addColorStop(0, this.color);
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(drawX, drawY, this.radius, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    const planetImages = [];
    const planetGlows = [
        'rgba(0, 255, 204, 0.5)', 
        'rgba(0, 204, 255, 0.5)', 
        'rgba(255, 100, 200, 0.3)', 
        'rgba(100, 150, 255, 0.3)',
        'rgba(255, 100, 50, 0.4)',  // Red gas
        'rgba(150, 255, 255, 0.4)', // Ice crystal
        'rgba(100, 255, 150, 0.4)'  // Shattered lava
    ];

    for (let i = 0; i < 7; i++) {
        const img = new Image();
        img.src = `/static/images/planets/planet_${i}.png`; 
        planetImages.push(img);
    }
    
    const sunImage = new Image();
    sunImage.src = '/static/images/planets/sun.png';

    const blackHoleImage = new Image();
    blackHoleImage.src = '/static/images/planets/blackhole.png';

    const galaxyImage = new Image();
    galaxyImage.src = '/static/images/planets/galaxy.png';

    class Planet {
        constructor(imgIndex) {
            this.reset();
            this.image = planetImages[imgIndex];
            this.glowColor = planetGlows[imgIndex];
            this.glitchTimer = 0;
        }
        reset() {
            const isLeftEdge = Math.random() > 0.5;
            this.x = isLeftEdge ? Math.random() * (width * 0.2) : width - Math.random() * (width * 0.2);
            this.y = Math.random() * height;
            this.z = Math.random() * 1.5 + 0.6; 
            this.radius = (Math.random() * 50 + 20) / this.z; 
            this.vx = (Math.random() - 0.5) * 0.1;
            this.vy = (Math.random() - 0.5) * 0.1;
            this.rotation = Math.random() * Math.PI * 2;
            this.rotationSpeed = (Math.random() - 0.5) * 0.002;
        }
        update() {
            this.x += (this.vx / this.z) * (warpSpeed > 1 ? warpSpeed * 0.5 : 1);
            this.y += (this.vy / this.z) * (warpSpeed > 1 ? warpSpeed * 0.5 : 1);
            this.rotation += this.rotationSpeed * warpSpeed;
            
            // Random Hologram Glitch trigger
            if (Math.random() < 0.002) this.glitchTimer = 15;
            if (this.glitchTimer > 0) this.glitchTimer--;

            if (this.x < -this.radius * 2) this.x = width + this.radius * 2;
            if (this.x > width + this.radius * 2) this.x = -this.radius * 2;
            if (this.y < -this.radius * 2) this.y = height + this.radius * 2;
            if (this.y > height + this.radius * 2) this.y = -this.radius * 2;
        }
        draw(px, py) {
            if (!this.image.complete || this.image.naturalWidth === 0) return;
            
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;

            ctx.save();
            ctx.translate(drawX, drawY);
            
            // Glow
            ctx.globalCompositeOperation = 'screen';
            let grad = ctx.createRadialGradient(0, 0, this.radius * 0.5, 0, 0, this.radius * 1.6);
            grad.addColorStop(0, this.glowColor);
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(0, 0, this.radius * 1.6, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.globalCompositeOperation = 'screen';
            ctx.rotate(this.rotation);
            
            // Hologram Glitch Effect
            if (this.glitchTimer > 0 && Math.random() > 0.3) {
                let offset = (Math.random() - 0.5) * 10;
                ctx.globalAlpha = 0.7;
                // Cyan split
                ctx.drawImage(this.image, -this.radius + offset, -this.radius, this.radius * 2, this.radius * 2);
                // Red/Green split
                ctx.globalCompositeOperation = 'screen';
                ctx.drawImage(this.image, -this.radius - offset, -this.radius + offset/2, this.radius * 2, this.radius * 2);
            } else {
                ctx.drawImage(this.image, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            }
            
            ctx.restore();
        }
    }

    class Sun {
        constructor() {
            this.x = width * 0.9;
            this.y = height * 0.1;
            this.radius = Math.min(width, height) * 0.12;
            this.z = 5; // Reduced z for stronger parallax
        }
        update() {}
        draw(px, py) {
            if (!sunImage.complete || sunImage.naturalWidth === 0) return;
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;
            
            ctx.save();
            ctx.translate(drawX, drawY);
            ctx.globalCompositeOperation = 'screen';
            
            // Draw realistic sun image
            ctx.drawImage(sunImage, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            
            // Extra outer glow
            let grad = ctx.createRadialGradient(0, 0, this.radius * 0.5, 0, 0, this.radius * 3);
            grad.addColorStop(0, 'rgba(255, 200, 50, 0)');
            grad.addColorStop(0.3, 'rgba(255, 120, 20, 0.5)');
            grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
            
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(0, 0, this.radius * 3, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.restore();
        }
    }

    class BlackHole {
        constructor() {
            this.x = width * 0.1;
            this.y = height * 0.9;
            this.radius = Math.min(width, height) * 0.15;
            this.z = 4; // Reduced z for stronger parallax
            this.rotation = 0;
        }
        update() {
            this.rotation += 0.005 * warpSpeed; // Slow rotation
        }
        draw(px, py) {
            if (!blackHoleImage.complete || blackHoleImage.naturalWidth === 0) return;
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;
            
            ctx.save();
            ctx.translate(drawX, drawY);
            ctx.globalCompositeOperation = 'screen';
            
            ctx.rotate(this.rotation);
            // Draw realistic black hole image
            ctx.drawImage(blackHoleImage, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            
            ctx.restore();
        }
    }

    class Galaxy {
        constructor() {
            this.x = width * 0.7;
            this.y = height * 0.8;
            this.radius = Math.min(width, height) * 0.35; // Massive
            this.z = 6; // Reduced z for stronger parallax
            this.rotation = Math.PI / 4;
        }
        update() {
            this.rotation -= 0.001 * warpSpeed; // Extremely slow majestic rotation
        }
        draw(px, py) {
            if (!galaxyImage.complete || galaxyImage.naturalWidth === 0) return;
            const drawX = this.x + px / this.z;
            const drawY = this.y + py / this.z;
            
            ctx.save();
            ctx.translate(drawX, drawY);
            ctx.globalCompositeOperation = 'screen';
            
            ctx.rotate(this.rotation);
            ctx.globalAlpha = 0.6; // Slightly transparent to look like background
            ctx.drawImage(galaxyImage, -this.radius, -this.radius, this.radius * 2, this.radius * 2);
            
            ctx.restore();
        }
    }

    class ShootingStar {
        constructor() { this.reset(); }
        reset() {
            this.active = false;
            if (Math.random() < 0.01) { 
                this.active = true;
                this.x = Math.random() * width * 1.5;
                this.y = -100;
                this.length = Math.random() * 200 + 100;
                this.speed = Math.random() * 15 + 10;
                this.angle = Math.PI / 4 + (Math.random() - 0.5) * 0.2; 
                this.opacity = Math.random() * 0.8 + 0.2;
            }
        }
        update() {
            if (!this.active) { this.reset(); return; }
            this.x -= Math.cos(this.angle) * this.speed * warpSpeed;
            this.y += Math.sin(this.angle) * this.speed * warpSpeed;
            if (this.x < -this.length || this.y > height + this.length) this.active = false;
        }
        draw(px, py) {
            if (!this.active) return;
            const drawX = this.x + px * 0.2;
            const drawY = this.y + py * 0.2;
            
            ctx.save();
            ctx.globalCompositeOperation = 'screen';
            
            let grad = ctx.createLinearGradient(drawX, drawY, drawX + Math.cos(this.angle) * this.length, drawY - Math.sin(this.angle) * this.length);
            grad.addColorStop(0, `rgba(255, 255, 255, ${this.opacity})`);
            grad.addColorStop(0.1, `rgba(0, 255, 204, ${this.opacity * 0.8})`);
            grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
            
            ctx.strokeStyle = grad;
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(drawX, drawY);
            ctx.lineTo(drawX + Math.cos(this.angle) * this.length, drawY - Math.sin(this.angle) * this.length);
            ctx.stroke();
            
            ctx.restore();
        }
    }

    class LightningBolt {
        constructor(x, y) {
            this.segments = [];
            this.alpha = 1.0;
            this.generate(x, y, 0);
        }
        
        generate(startX, startY, depth) {
            let x = startX;
            let y = startY;
            let path = [{x, y}];
            while(y < height && path.length < 50) {
                x += (Math.random() - 0.5) * 80;
                y += Math.random() * 60 + 20;
                path.push({x, y});
                if (Math.random() < 0.2 && depth < 2) {
                    this.segments.push(this.createBranch(x, y, depth + 1));
                }
            }
            this.segments.push(path);
        }

        createBranch(startX, startY, depth) {
            let x = startX;
            let y = startY;
            let path = [{x, y}];
            let length = Math.random() * 200 + 100;
            let currentLength = 0;
            let angle = (Math.random() - 0.5) * Math.PI * 0.8; 
            
            while(currentLength < length) {
                let dist = Math.random() * 40 + 10;
                currentLength += dist;
                x += Math.sin(angle) * dist + (Math.random() - 0.5) * 30;
                y += Math.cos(angle) * dist + Math.random() * 20;
                path.push({x, y});
            }
            return path;
        }

        draw() {
            ctx.save();
            ctx.globalCompositeOperation = 'screen';
            
            ctx.beginPath();
            for (let path of this.segments) {
                ctx.moveTo(path[0].x, path[0].y);
                for (let i = 1; i < path.length; i++) {
                    ctx.lineTo(path[i].x, path[i].y);
                }
            }
            
            ctx.strokeStyle = `rgba(0, 204, 255, ${this.alpha * 0.2})`;
            ctx.lineWidth = 15;
            ctx.stroke();

            ctx.strokeStyle = `rgba(0, 255, 204, ${this.alpha * 0.5})`;
            ctx.lineWidth = 6;
            ctx.stroke();
            
            ctx.strokeStyle = `rgba(255, 255, 255, ${this.alpha})`;
            ctx.lineWidth = 2;
            ctx.stroke();

            ctx.restore();
            this.alpha -= 0.05;
        }
    }

    let activeLightnings = [];
    let sun, blackHole, galaxy;
    let shootingStars = [];

    function initElements() {
        nodes = [];
        planets = [];
        nebulas = [];
        shootingStars = [];
        sun = new Sun();
        blackHole = new BlackHole();
        galaxy = new Galaxy();

        const area = width * height;
        const numNodes = Math.min(Math.floor(area / 12000), 80); 
        
        for (let i = 0; i < numNodes; i++) nodes.push(new Node());
        for (let i = 0; i < 4; i++) nebulas.push(new Nebula());
        for (let i = 0; i < 14; i++) planets.push(new Planet(i % 7)); // 7 unique planets now
        for (let i = 0; i < 4; i++) shootingStars.push(new ShootingStar());
    }

    function drawRadar() {
        radarRadius += 2 * warpSpeed;
        const maxRadius = Math.max(width, height);
        
        if (radarRadius > maxRadius) radarRadius = 0;

        const opacity = 0.05 * (1 - radarRadius / maxRadius);
        ctx.beginPath();
        ctx.arc(centerX, centerY, radarRadius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0, 255, 204, ${opacity})`;
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    function animate() {
        // Deep background
        ctx.fillStyle = colors.bg;
        ctx.fillRect(0, 0, width, height);

        // Lightning flash effect (Extremely rare, approx once every 5 minutes)
        if (Math.random() < 0.00005) {
            lightningFlash = 1.0;
            activeLightnings.push(new LightningBolt(Math.random() * width, 0));
        }
        if (lightningFlash > 0) {
            ctx.fillStyle = `rgba(180, 230, 255, ${lightningFlash * 0.1})`;
            ctx.fillRect(0, 0, width, height);
            lightningFlash -= 0.04;
            // Secondary strike
            if (Math.random() < 0.1 && lightningFlash < 0.5) {
                lightningFlash = 0.7;
                activeLightnings.push(new LightningBolt(Math.random() * width, 0));
            }
        }
        
        for (let i = activeLightnings.length - 1; i >= 0; i--) {
            activeLightnings[i].draw();
            if (activeLightnings[i].alpha <= 0) {
                activeLightnings.splice(i, 1);
            }
        }

        // Smooth Warp Speed transition
        const targetWarp = isWarping ? 12 : 1;
        warpSpeed += (targetWarp - warpSpeed) * 0.05;

        mouse.currentX += (mouse.targetX - mouse.currentX) * 0.05;
        mouse.currentY += (mouse.targetY - mouse.currentY) * 0.05;
        
        const px = mouse.currentX * -1;
        const py = mouse.currentY * -1;

        // 1. Nebulas
        for (let n of nebulas) { n.update(); n.draw(px, py); }

        // 2. Radar Sweep
        drawRadar();

        // 3. Network Nodes & Connections
        ctx.globalCompositeOperation = 'screen';
        if (warpSpeed < 3) {
            for (let i = 0; i < nodes.length; i++) {
                const n1 = nodes[i];
                n1.update(); // Update positions once here
                const x1 = n1.x + px / n1.z;
                const y1 = n1.y + py / n1.z;
    
                for (let j = i + 1; j < nodes.length; j++) {
                    const n2 = nodes[j];
                    const x2 = n2.x + px / n2.z;
                    const y2 = n2.y + py / n2.z;
    
                    const distSq = (x1 - x2)*(x1 - x2) + (y1 - y2)*(y1 - y2);
                    if (distSq < 15000) { 
                        const opacity = 1 - (Math.sqrt(distSq) / 122.5); // Dynamic opacity
                        ctx.beginPath();
                        ctx.moveTo(x1, y1);
                        ctx.lineTo(x2, y2);
                        ctx.strokeStyle = `rgba(0, 255, 204, ${opacity * 0.6})`;
                        ctx.lineWidth = opacity * 1.5;
                        ctx.stroke();
                    }
                }
            }
            
            // Mouse connection in a separate path
            if (mouse.screenX !== -1000 && mouse.screenY !== -1000) {
                ctx.beginPath();
                for (let i = 0; i < nodes.length; i++) {
                    const n1 = nodes[i];
                    const x1 = n1.x + px / n1.z;
                    const y1 = n1.y + py / n1.z;
                    const mDistSq = (x1 - mouse.screenX)*(x1 - mouse.screenX) + (y1 - mouse.screenY)*(y1 - mouse.screenY);
                    if (mDistSq < 30000) {
                        const mOpacity = 1 - (Math.sqrt(mDistSq) / 173);
                        ctx.moveTo(x1, y1);
                        ctx.lineTo(mouse.screenX, mouse.screenY);
                        ctx.strokeStyle = `rgba(0, 255, 204, ${mOpacity * 0.8})`;
                        ctx.stroke();
                        ctx.beginPath(); // Reset for next line
                    }
                }
            }
        } else {
            // If warp speed is high, still update nodes
            for (let i = 0; i < nodes.length; i++) {
                nodes[i].update();
            }
        }

        // Step 3.2: Draw the nodes (circles)
        for (let i = 0; i < nodes.length; i++) {
            nodes[i].draw(px, py);
        }

        // 4. Planets
        for (let p of planets) { p.update(); p.draw(px, py); }
        
        // 4.5 Celestial Bodies
        if(galaxy) { galaxy.update(); galaxy.draw(px, py); }
        if(sun) { sun.update(); sun.draw(px, py); }
        if(blackHole) { blackHole.update(); blackHole.draw(px, py); }
        for (let s of shootingStars) { s.update(); s.draw(px, py); }

        requestAnimationFrame(animate);
    }

    resize();
    animate();
});
