(()=>{
 let preference=null;try{preference=localStorage.getItem('job-tracker-theme');}catch{}
 const system=matchMedia('(prefers-color-scheme: dark)');
 const apply=theme=>{document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme;const b=document.querySelector('#themeToggle');if(b){b.textContent=theme==='dark'?'Light mode':'Dark mode';b.setAttribute('aria-label',theme==='dark'?'Switch to light mode':'Switch to dark mode');b.setAttribute('aria-pressed',String(theme==='dark'));}};
 apply(preference|| (system.matches?'dark':'light'));
 document.addEventListener('DOMContentLoaded',()=>{apply(document.documentElement.dataset.theme);document.querySelector('#themeToggle').onclick=()=>{preference=document.documentElement.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('job-tracker-theme',preference);}catch{}apply(preference);};});
 system.addEventListener('change',e=>{if(!preference)apply(e.matches?'dark':'light');});
})();
