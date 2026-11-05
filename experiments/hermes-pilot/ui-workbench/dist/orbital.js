export class Orbital {
 constructor(canvas){this.canvas=canvas;this.ctx=canvas.getContext('2d');this.phase='idle';this.expansion=0;this.energy=0;this.time=0;this.last=0;this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;this.animate=this.animate.bind(this);requestAnimationFrame(this.animate)}
 setPhase(phase){this.phase=phase}
 setEnergy(level){this.energy=level}
 animate(time){requestAnimationFrame(this.animate);if(time-this.last<33||document.hidden)return;this.last=time;this.time=time/1000;const target=this.phase==='expanding'?1:0;this.expansion+=(target-this.expansion)*.065;this.draw()}
 draw(){const c=this.ctx,W=this.canvas.width,H=this.canvas.height,t=this.reduced?0:this.time;c.clearRect(0,0,W,H);c.save();c.translate(W/2,H/2);const e=this.expansion,scale=1+this.energy*.04;
 c.scale(scale,scale);const glow=c.createRadialGradient(0,0,80,0,0,380);glow.addColorStop(0,'#0879df06');glow.addColorStop(.58,'#098eff0b');glow.addColorStop(1,'#098eff00');c.fillStyle=glow;c.fillRect(-450,-450,900,900);
 if(e>.01){for(let ring=0;ring<7;ring++){c.beginPath();for(let i=0;i<=180;i++){const a=i/180*Math.PI*2;let x=Math.cos(a)*250,y=Math.sin(a)*250,z=(ring-3)*95*e;const yaw=e*.95,pitch=e*-.28;let X=x*Math.cos(yaw)+z*Math.sin(yaw),Z=-x*Math.sin(yaw)+z*Math.cos(yaw),Y=y*Math.cos(pitch)-Z*Math.sin(pitch);let q=900/(900+Z);if(i===0)c.moveTo(X*q,Y*q);else c.lineTo(X*q,Y*q)}c.strokeStyle=ring===3?'#6bddff':`rgba(37,138,255,${.12+(.5-Math.abs(ring-3)*.1)*e})`;c.lineWidth=ring===3?3:1;c.shadowColor='#168fff';c.shadowBlur=ring===3?14:0;c.stroke()}c.shadowBlur=0}
 const fade=1-e*.85;c.globalAlpha=fade;
 for(let ring=0;ring<5;ring++){const r=238+ring*23; c.strokeStyle=['#2684b035','#3b9ed94a','#3899c42b','#258aff38','#488fb62e'][ring];c.lineWidth=ring===1?2:1;c.beginPath();c.arc(0,0,r,0,Math.PI*2);c.stroke()}
 for(let i=0;i<180;i++){let a=i/180*Math.PI*2+t*.012;const r=344,len=i%15===0?17:i%5===0?10:4;c.strokeStyle=i%5===0?'#71caff9c':'#3295d64a';c.lineWidth=i%15===0?2:1;c.beginPath();c.moveTo(Math.cos(a)*r,Math.sin(a)*r);c.lineTo(Math.cos(a)*(r+len),Math.sin(a)*(r+len));c.stroke()}
 for(let i=0;i<4;i++){const start=t*(i%2?.12:-.09)+i*1.75; c.strokeStyle=i%2?'#288bdb':'#8be8ff';c.lineWidth=i%2?3:5;c.shadowBlur=i%2?7:18;c.shadowColor='#238fff';c.beginPath();c.arc(0,0,i%2?306:272,start,start+(i%2?.42:.77));c.stroke()}c.shadowBlur=0;
 for(let i=0;i<4;i++){const a=i*Math.PI/2;c.strokeStyle='#76d6ff7a';c.lineWidth=1;c.beginPath();c.moveTo(Math.cos(a)*220,Math.sin(a)*220);c.lineTo(Math.cos(a)*385,Math.sin(a)*385);c.stroke()}
 c.setLineDash([1,12]);c.strokeStyle='#4385af88';c.beginPath();c.arc(0,0,225,0,Math.PI*2);c.stroke();c.setLineDash([]);
 c.strokeStyle='#60d4ff77';c.lineWidth=2;for(const sx of [-1,1])for(const sy of [-1,1]){c.beginPath();c.moveTo(sx*368,sy*336);c.lineTo(sx*368,sy*368);c.lineTo(sx*336,sy*368);c.stroke()}
 c.restore()}
}
