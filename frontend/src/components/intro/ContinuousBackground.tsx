import React, { useEffect, useRef } from 'react';

export const ContinuousBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    // Particle nodes for data lineage graph effect
    const nodeCount = Math.min(Math.floor((width * height) / 24000), 45);
    const nodes: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      radius: number;
      color: string;
      glowColor: string;
      alpha: number;
      pulseSpeed: number;
      pulsePhase: number;
    }> = [];

    const palette = [
      { color: 'rgba(56, 189, 248, ', glow: '#38bdf8' },  // Cyan Lineage
      { color: 'rgba(52, 211, 153, ', glow: '#34d399' },  // Emerald Verified
      { color: 'rgba(168, 85, 247, ', glow: '#a855f7' },  // Purple AI
      { color: 'rgba(251, 191, 36, ', glow: '#fbbf24' },  // Amber Alert
    ];

    for (let i = 0; i < nodeCount; i++) {
      const p = palette[Math.floor(Math.random() * palette.length)];
      nodes.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        radius: Math.random() * 1.8 + 1,
        color: p.color,
        glowColor: p.glow,
        alpha: Math.random() * 0.4 + 0.2,
        pulseSpeed: 0.015 + Math.random() * 0.02,
        pulsePhase: Math.random() * Math.PI * 2,
      });
    }

    let mouseX = -1000;
    let mouseY = -1000;

    const handleMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    };

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    window.addEventListener('resize', handleResize);

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // Connect nearby nodes
      for (let i = 0; i < nodes.length; i++) {
        const nodeA = nodes[i];

        nodeA.x += nodeA.vx;
        nodeA.y += nodeA.vy;

        // Bounce smoothly
        if (nodeA.x < 0 || nodeA.x > width) nodeA.vx *= -1;
        if (nodeA.y < 0 || nodeA.y > height) nodeA.vy *= -1;

        nodeA.pulsePhase += nodeA.pulseSpeed;
        const currentAlpha = nodeA.alpha + Math.sin(nodeA.pulsePhase) * 0.15;

        // Mouse gentle interaction
        const dxMouse = nodeA.x - mouseX;
        const dyMouse = nodeA.y - mouseY;
        const distMouse = Math.sqrt(dxMouse * dxMouse + dyMouse * dyMouse);
        if (distMouse < 130 && distMouse > 0) {
          const force = (130 - distMouse) / 130;
          nodeA.x += (dxMouse / distMouse) * force * 0.5;
          nodeA.y += (dyMouse / distMouse) * force * 0.5;
        }

        // Draw node
        ctx.beginPath();
        ctx.arc(nodeA.x, nodeA.y, nodeA.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${nodeA.color}${Math.max(0.1, currentAlpha)})`;
        ctx.shadowBlur = 5;
        ctx.shadowColor = nodeA.glowColor;
        ctx.fill();
        ctx.shadowBlur = 0;

        // Draw edge connections
        for (let j = i + 1; j < nodes.length; j++) {
          const nodeB = nodes[j];
          const dx = nodeA.x - nodeB.x;
          const dy = nodeA.y - nodeB.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          const maxDist = 120;
          if (dist < maxDist) {
            const lineAlpha = (1 - dist / maxDist) * 0.12;
            ctx.beginPath();
            ctx.moveTo(nodeA.x, nodeA.y);
            ctx.lineTo(nodeB.x, nodeB.y);
            ctx.strokeStyle = `rgba(56, 189, 248, ${lineAlpha})`;
            ctx.lineWidth = 0.6;
            ctx.stroke();
          }
        }
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden select-none">
      
      {/* 1. Base Dark Midnight Color */}
      <div className="absolute inset-0 bg-[#070b14]" />

      {/* 2. Global Cinematic Background Looping Video */}
      <div className="absolute inset-0 z-0 overflow-hidden">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="w-full h-full object-cover opacity-60 mix-blend-screen pointer-events-none filter brightness-90 contrast-125"
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260508_064122_c4750c0e-7476-4b44-94a2-a85a65c63bf2.mp4"
        />
        {/* Cinematic dark tint overlay to preserve contrast for diagrams */}
        <div className="absolute inset-0 bg-[#070b14]/75 pointer-events-none" />
      </div>

      {/* 3. Two Fixed Vertical Guide Lines at 36rem Container Edges */}
      <div className="hidden md:block pointer-events-none fixed inset-y-0 left-1/2 -translate-x-[calc(50%+36rem)] w-px bg-white/10 z-[5]" />
      <div className="hidden md:block pointer-events-none fixed inset-y-0 left-1/2 translate-x-[calc(-50%+36rem)] w-px bg-white/10 z-[5]" />

      {/* 4. High-Tech Precision Dot Matrix Grid */}
      <div 
        className="absolute inset-0 opacity-[0.12] pointer-events-none z-[6]"
        style={{
          backgroundImage: 'radial-gradient(#38bdf8 0.75px, transparent 0.75px)',
          backgroundSize: '24px 24px',
        }}
      />

      {/* 5. Canvas Data Particle Nodes & Mesh */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full opacity-65 z-[7]"
      />

      {/* 6. Radial Vignette for Content Center Focus */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_35%,rgba(7,11,20,0.85)_100%)] pointer-events-none z-[8]" />
    </div>
  );
};
