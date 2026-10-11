import html, json
CSS="""
:root{--bg:#131a16;--card:#162217;--card2:#0f1612;--line:rgba(215,242,44,.10);--line2:rgba(215,242,44,.2);--acc:#D7F22C;--blue:#4FC3F7;--t:#fff;--ts:#9AA69A;--td:#6C7A6C;--bad:#EF6B5D;--hard:#3AA0FF;--clay:#FF8A3D;--grass:#3ED66B}

header.nav{position:sticky;top:0;z-index:50;display:flex;align-items:center;justify-content:space-between;padding:22px 32px;background:rgba(19,26,22,.82);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none}.brand-mark{width:34px;height:34px;display:flex;align-items:center;justify-content:center;color:var(--acc)}.brand-mark svg{width:34px;height:34px}.brand-name{font-family:Unbounded,Inter,sans-serif;font-weight:700;font-size:19px;color:var(--acc)}
.nav-right{display:flex;align-items:center;gap:22px}.lang-dropdown{position:relative}.lang-dropdown summary{list-style:none}.lang-dropdown summary::after{content:none!important}.lang-dropdown summary::-webkit-details-marker{display:none}
.lang-select{display:flex;align-items:center;gap:9px;background:rgba(255,255,255,.05);border:1px solid var(--line2);border-radius:999px;padding:9px 16px 9px 18px;font-size:13.5px;font-weight:600;color:#fff;cursor:pointer}.lang-select svg{width:12px;height:12px;color:var(--ts)}
.lang-menu{position:absolute;top:calc(100% + 8px);right:0;min-width:160px;background:#0c110e;border:1px solid var(--line2);border-radius:14px;padding:6px;box-shadow:0 20px 40px -14px rgba(0,0,0,.7);z-index:60}.lang-option{display:block;padding:10px 14px;border-radius:9px;color:#fff;font-size:13.5px;font-weight:600;text-decoration:none}.lang-option:hover{background:rgba(215,242,44,.12);color:var(--acc)}.lang-option.active{color:var(--acc)}
.nav-login{display:flex;align-items:center;gap:8px;font-family:Unbounded,Inter,sans-serif;font-weight:700;font-size:13.5px;letter-spacing:.04em;color:#fff;text-transform:uppercase;text-decoration:none}.nav-login:hover{color:var(--acc)}.nav-login .chev{display:flex;color:var(--acc)}.nav-login .chev svg{width:15px;height:15px}.nav-login-mobile{display:none}
@media(max-width:760px){footer{padding:40px 18px 36px!important}header.nav{padding:16px 18px}.lang-select,.nav-login{display:none}.nav-login-mobile{display:inline-flex;align-items:center;justify-content:center;background:var(--acc);color:var(--bg);border-radius:999px;padding:9px 16px;font-family:Unbounded,Inter,sans-serif;font-weight:800;font-size:13px;white-space:nowrap;text-decoration:none}}
footer{background:linear-gradient(180deg,transparent 0%,rgba(12,17,14,.55) 100%);padding:56px 32px 44px;border-top:0;margin-top:40px}.foot-wrap{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;max-width:1180px;margin:0 auto}.foot-links{display:flex;flex-wrap:wrap;gap:12px 26px;color:var(--ts);font-size:13.5px}.foot-links a{text-decoration:none}.foot-copy{color:var(--td);font-size:12.5px}.foot-note{max-width:1180px;margin:22px auto 0;color:var(--td);font-size:12px}
*{box-sizing:border-box}body{margin:0;color:var(--t);font:16px/1.55 Inter,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;background:radial-gradient(ellipse 900px 480px at 50% 210px,rgba(215,242,44,.10),transparent 70%),radial-gradient(ellipse 1200px 620px at 50% 780px,rgba(215,242,44,.05),transparent 65%),var(--bg);background-repeat:no-repeat;background-attachment:scroll}h1,h2,.pct,.res .sc{font-family:Unbounded,Inter,sans-serif}
a{color:inherit}.wrap{max-width:860px;margin:0 auto;padding:0 18px}main.wrap{padding-top:6px;padding-bottom:10px}.card,.lockcard,.bigcta{margin-bottom:22px}
.btn{background:var(--acc);color:#0b110c;font-weight:800;border-radius:9px;padding:11px 18px;text-decoration:none;font-size:14px;display:inline-block}
.btn.ghost{background:transparent;color:var(--acc);border:1.5px solid var(--acc)}
.crumb{font-size:12.5px;color:var(--td);padding:16px 0 4px}.crumb a{color:var(--ts);text-decoration:none}
h1{font-size:clamp(26px,5vw,38px);line-height:1.15;margin:6px 0 12px;font-weight:800;letter-spacing:-.5px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}.chip{font-size:13px;font-weight:600;border:1px solid var(--line);border-left:3px solid var(--acc);background:rgba(255,255,255,.03);color:#dfe7df;border-radius:6px;padding:6px 12px}
.chip.surf{border-left-color:var(--surf)}
.card{background:linear-gradient(180deg,var(--card),var(--card2));border:1px solid var(--line);border-radius:14px;padding:22px;margin:0 0 18px}
.card h2{font-size:13px;letter-spacing:1.6px;text-transform:uppercase;color:var(--acc);margin:0 0 16px;font-weight:800}
.vs{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;text-align:center}
.pl .ph{width:112px;height:140px;border-radius:10px;margin:0 auto 10px;background:#1f2e22;border:1px solid var(--line2);object-fit:cover;object-position:50% 12%;display:block;filter:saturate(.9)}
.pl.fav .ph{border:2px solid var(--acc)}
.pl b{display:block;font-size:18px}.pl small{color:var(--ts);font-size:12.5px}
.pct{font-size:clamp(40px,9vw,64px);font-weight:900;line-height:1;margin-top:8px;color:var(--ts)}.pl.fav .pct{background:linear-gradient(135deg,#ff7a45,#ffb020,#ff5f6d);-webkit-background-clip:text;color:transparent}
.mid{color:var(--td);font-weight:800;font-size:14px}
.bar{height:10px;border-radius:3px;background:#243126;overflow:hidden;margin:22px 0 6px;display:flex}.bar i{display:block;height:100%;background:linear-gradient(90deg,#ff7a45,#ffb020)}
.legend{display:flex;justify-content:space-between;font-size:12.5px;color:var(--ts)}
.res{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:18px;padding-top:16px;border-top:1px dashed var(--line2)}
.res .sc{font-size:26px;font-weight:900;letter-spacing:1px}.res small{display:block;color:var(--ts);font-size:12.5px;font-weight:500;letter-spacing:0}
.badge{font-weight:800;font-size:13px;letter-spacing:.5px;text-transform:uppercase;border-radius:6px;padding:9px 14px}.badge.ok{background:rgba(62,214,107,.14);color:var(--grass);border:1px solid var(--grass)}.badge.ko{background:rgba(239,107,93,.14);color:var(--bad);border:1px solid var(--bad)}
.pend{font-size:13.5px;color:var(--ts)}
table{width:100%;border-collapse:collapse;font-size:14.5px}th,td{padding:11px 6px;border-bottom:1px solid var(--line);text-align:center}th{font-weight:700;color:var(--ts);font-size:12.5px}td:nth-child(2){color:var(--ts);font-size:12.5px;font-weight:600}tr:last-child td{border-bottom:0}
.form{display:inline-flex;gap:4px}.form span{width:20px;height:20px;border-radius:5px;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;color:#0b110c}.form .w{background:var(--grass)}.form .l{background:var(--bad)}
.analysis p{margin:0 0 12px;color:#dfe7df}
.lock{position:relative;overflow:hidden}.lock .blur{filter:blur(7px);opacity:.55;pointer-events:none;user-select:none}
.lock .cta{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;padding:18px;background:linear-gradient(180deg,rgba(15,22,18,.15),rgba(15,22,18,.78))}
.lock .cta b{font-size:18px}.lock .cta span{font-size:13.5px;color:var(--ts)}
.proj{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;text-align:center}.proj div{background:#1a2a1d;border-radius:14px;padding:14px 6px}.proj b{display:block;font-size:22px}.proj small{color:var(--ts);font-size:12px}
details{border-bottom:1px solid var(--line);padding:14px 0}details:last-child{border:0}summary{cursor:pointer;font-weight:700;list-style:none}summary::after{content:"+";float:right;color:var(--acc)}details[open] summary::after{content:"–"}details p{margin:10px 0 0;color:#cdd6cd;font-size:15px}
.rel{display:grid;gap:10px}.rel a{display:flex;justify-content:space-between;gap:10px;text-decoration:none;background:#182519;border:1px solid var(--line);border-radius:14px;padding:13px 16px;font-weight:600;font-size:15px}.rel a span{color:var(--acc);font-weight:800}
.bigcta{background:var(--acc);color:#0b110c;border-radius:14px;padding:30px 24px;margin:30px 0 26px;display:flex;align-items:center;justify-content:space-between;gap:22px;flex-wrap:wrap;box-shadow:0 0 0 6px rgba(215,242,44,.10),0 18px 50px rgba(215,242,44,.12)}.bigcta .bc-t{flex:1 1 320px}.bc-k{font-size:12px;font-weight:800;letter-spacing:1.6px;text-transform:uppercase;opacity:.7}.btn.dark{background:#0b110c;color:var(--acc);padding:15px 22px;font-size:15px;white-space:nowrap}
.bigcta h2{font-size:clamp(20px,4.5vw,28px);line-height:1.2;margin:8px 0 10px;color:#0b110c;letter-spacing:-.3px;text-transform:none}.bigcta p{margin:0;font-size:15px;font-weight:500;color:#1d2a10}
footer{border-top:1px solid var(--line);margin-top:40px;padding:26px 0 40px;font-size:12.5px;color:var(--td)}footer a{color:var(--ts)}
.sr{position:absolute;left:-9999px}.wx{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.wx div{background:#1a2a1d;border:1px solid var(--line);border-radius:10px;padding:14px 8px;text-align:center}.wx b{display:block;font-size:17px;font-family:Unbounded,Inter,sans-serif}.wx small{color:var(--ts);font-size:12px}.wxn{margin:14px 0 0;color:#dfe7df;font-size:15px}@media(max-width:520px){.wx{grid-template-columns:repeat(2,1fr)}}.sc2{margin-top:20px;padding-top:16px;border-top:1px dashed var(--line2)}.sc2h{font-size:12.5px;letter-spacing:1.2px;text-transform:uppercase;font-weight:800;color:var(--ts);margin-bottom:12px}.sc2h small{text-transform:none;letter-spacing:0;font-weight:500;color:var(--td);margin-left:6px}.sc2g{display:grid;grid-template-columns:1fr 1fr;gap:10px}.sct{background:#1a2a1d;border:1px solid var(--line);border-radius:10px;padding:13px 12px;position:relative}.sct .ss{display:block;font-size:12.5px;color:var(--ts);font-weight:600}.sct b{display:block;font-size:19px;margin:3px 0 2px;font-family:Unbounded,Inter,sans-serif;letter-spacing:.3px}.sct small{color:var(--td);font-size:12px}.sct em{display:block;margin-top:8px;font-style:normal;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.6px}.sct.hit{border:2px solid var(--grass);background:rgba(62,214,107,.10)}.sct.hit em{color:var(--grass)}.sct.near{border-color:var(--acc)}.sct.near em{color:var(--acc)}@media(max-width:520px){.sct b{font-size:16px}}.sccard h2{margin-bottom:18px}.final{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;background:linear-gradient(135deg,rgba(215,242,44,.14),rgba(215,242,44,.04));border:1px solid var(--line2);border-radius:12px;padding:20px;margin-bottom:22px}.final small{display:block;color:var(--ts);font-size:12.5px}.final .fs{font-family:Unbounded,Inter,sans-serif;font-weight:900;font-size:clamp(30px,8vw,44px);line-height:1.1;margin:4px 0}.final>div>span{color:#dfe7df;font-size:14px}.fp{display:flex;gap:22px}.fp b{display:block;font-family:Unbounded,Inter,sans-serif;font-size:26px;background:linear-gradient(135deg,#ff7a45,#ffb020);-webkit-background-clip:text;color:transparent}.fp small{max-width:150px}
.sct{padding:16px 14px!important}.sct .sn{display:block;font-size:11.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--td);font-weight:800}.sct .sp{font-family:Unbounded,Inter,sans-serif;font-weight:900;font-size:34px;line-height:1.1;margin:6px 0 2px;background:linear-gradient(135deg,#ff7a45,#ffb020,#ff5f6d);-webkit-background-clip:text;color:transparent}.sct.near{border:2px solid var(--clay)!important;background:rgba(255,138,61,.10)}.sct.near em{color:var(--clay)}
.lockbox{position:relative;overflow:hidden;border-radius:14px;margin:0 0 18px;min-height:230px;background:linear-gradient(135deg,#ff7a45 0%,#ffb020 45%,#D7F22C 100%)}.lk-blur{position:absolute;inset:0;padding:24px;filter:blur(7px);opacity:1}.lk-row i{display:block;height:16px;border-radius:4px;background:rgba(11,17,12,.55);margin-bottom:14px}.lk-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:20px}.lk-tiles div{background:rgba(255,255,255,.55);border-radius:10px;padding:22px 8px;text-align:center}.lk-tiles b{font-size:26px;color:#0b110c}
.lk-cta{position:relative;z-index:2;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:10px;padding:34px 22px;min-height:230px;color:#fff}.lk-pan{background:rgba(11,17,12,.80);border:1px solid rgba(255,255,255,.14);border-radius:12px;padding:22px 20px;max-width:440px;display:flex;flex-direction:column;align-items:center;gap:10px;backdrop-filter:blur(2px)}.lk-cta h2{margin:0;font-size:clamp(18px,4.5vw,24px);color:#fff;text-transform:none;letter-spacing:-.2px;line-height:1.25}.lk-cta p{margin:0;font-size:14px;color:#e8efe8;max-width:440px}.lk-cta svg{color:var(--acc)}.sct{display:flex!important;align-items:center;justify-content:space-between;gap:14px;padding:18px 18px!important}.sct .sl{min-width:0}.sct .sn{display:block;font-size:12px;letter-spacing:.6px;text-transform:uppercase;color:var(--ts);font-weight:700;margin-bottom:6px}.sct b.sg{display:block;font-family:Unbounded,Inter,sans-serif;font-weight:900;font-size:clamp(22px,6vw,30px);line-height:1.15;margin:0;letter-spacing:0;color:#fff;white-space:nowrap}.sct .sp{font-size:19px!important;font-weight:800;margin:0!important;text-align:right;white-space:nowrap;font-family:Inter,sans-serif!important}.sct .sp::after{content:"";display:block}.sct em{margin-top:8px!important}.sc2g{grid-template-columns:1fr 1fr}@media(max-width:620px){.sc2g{grid-template-columns:1fr}}.lockcard{position:relative;overflow:hidden;padding:0}.lk-body{padding:22px 22px 28px;min-height:420px;filter:blur(6px);user-select:none;pointer-events:none}.lk-body h2{margin-bottom:14px}.fac{margin-top:14px}.fh{font-size:13px;color:var(--ts);font-weight:700;margin-bottom:10px}.fr{display:flex;align-items:center;gap:12px;margin-bottom:10px;font-size:14px}.fr span{width:110px;color:#dfe7df}.fr i{display:block;height:14px;border-radius:3px;background:linear-gradient(90deg,#ff7a45,#ffb020,#D7F22C)}.al{margin:14px 0 0;color:#dfe7df;font-size:14px}.lk-over{position:absolute;inset:0;display:flex;align-items:flex-start;justify-content:center;padding:18px 16px;background:rgba(15,22,18,.2)}.lk-pan{background:rgba(11,17,12,.88);border:1px solid var(--line2);border-radius:12px;padding:20px 20px;max-width:380px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:8px}.lk-pan svg{color:var(--acc)}.lk-pan b{font-size:17px;line-height:1.3}.lk-pan span{font-size:13.5px;color:var(--ts)}.lk-pan .btn{margin-top:6px}.tpl{background:#2a1f10;color:#ffb020;font-size:12px;text-align:center;padding:6px;font-weight:700}
details.past{border:0;padding:0;margin:0 0 22px}details.past summary{display:inline-block;list-style:none;cursor:pointer}details.past summary::after{content:none!important}.dh{font-size:12.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--ts);font-weight:800;margin:20px 0 10px}.dh:first-child{margin-top:0}.mrow{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#182519;border:1px solid var(--line);border-radius:14px;padding:12px 16px;text-decoration:none;margin-bottom:10px}.mrow:hover{border-color:var(--line2)}.mrow .t{min-width:0}.mrow .t b{display:block;font-size:15px;font-weight:700}.mrow .t small{color:var(--td);font-size:12.5px;font-weight:500}.mrow .pp{display:flex;align-items:center;gap:10px;flex:none}.mrow img{width:44px;height:56px;border-radius:8px;object-fit:cover;object-position:50% 12%;background:#1f2e22;border:1px solid var(--line2);display:block}.mrow .pv{font-family:Unbounded,Inter,sans-serif;font-weight:800;font-size:15px;min-width:58px;text-align:center;color:var(--clay);white-space:nowrap}.mrow .pv.ok{color:var(--grass)}.mrow .pv.ko{color:var(--bad)}.mrow .pv small{display:block;font-family:Inter,sans-serif;font-size:11px;font-weight:600;color:var(--ts)}@media(max-width:520px){.mrow{padding:10px 12px}.mrow img{width:38px;height:48px}.mrow .pv{min-width:48px;font-size:13px}}
@media(max-width:520px){.card{padding:18px}.pl .ph{width:92px;height:116px}.pl b{font-size:16px}}
"""
BRAND='<span class="brand-mark"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="currentColor"/><path d="M 11.07,1.11 L 11.14,1.32 L 11.25,1.54 L 11.50,1.75 L 11.78,1.97 L 12.04,2.19 L 12.29,2.40 L 12.47,2.62 L 12.65,2.83 L 12.83,3.05 L 12.97,3.26 L 13.11,3.48 L 13.22,3.70 L 13.29,3.91 L 13.37,4.13 L 13.44,4.34 L 13.47,4.56 L 13.51,4.77 L 13.55,4.99 L 13.55,5.21 L 13.55,5.42 L 13.55,5.64 L 13.51,5.85 L 13.47,6.07 L 13.44,6.28 L 13.40,6.50 L 13.37,6.72 L 13.29,6.93 L 13.22,7.15 L 13.15,7.36 L 13.08,7.58 L 13.01,7.79 L 12.93,8.01 L 12.83,8.23 L 12.75,8.44 L 12.65,8.66 L 12.54,8.87 L 12.43,9.09 L 12.32,9.30 L 12.22,9.52 L 12.11,9.74 L 12.00,9.95 L 11.89,10.17 L 11.78,10.38 L 11.68,10.60 L 11.53,10.81 L 11.42,11.03 L 11.32,11.25 L 11.17,11.46 L 11.07,11.68 L 10.96,11.89 L 10.85,12.11 L 10.71,12.32 L 10.60,12.54 L 10.49,12.75 L 10.38,12.97 L 10.24,13.19 L 10.13,13.40 L 10.02,13.62 L 9.92,13.83 L 9.81,14.05 L 9.74,14.26 L 9.63,14.48 L 9.52,14.70 L 9.41,14.91 L 9.34,15.13 L 9.23,15.34 L 9.16,15.56 L 9.09,15.77 L 9.02,15.99 L 8.94,16.21 L 8.87,16.42 L 8.80,16.64 L 8.76,16.85 L 8.69,17.07 L 8.66,17.28 L 8.62,17.50 L 8.58,17.72 L 8.55,17.93 L 8.55,18.15 L 8.51,18.36 L 8.51,18.58 L 8.51,18.79 L 8.51,19.01 L 8.55,19.23 L 8.55,19.44 L 8.58,19.66 L 8.62,19.87 L 8.69,20.09 L 8.73,20.30 L 8.80,20.52 L 8.87,20.74 L 8.98,20.95 L 9.09,21.17 L 9.20,21.38 L 9.30,21.60 L 9.45,21.81 L 9.59,22.03 L 9.77,22.25 L 9.95,22.46 L 10.13,22.68 L 10.31,22.86 L 12.90,22.86 L 12.86,22.68 L 12.72,22.46 L 12.50,22.25 L 12.22,22.03 L 11.96,21.81 L 11.71,21.60 L 11.53,21.38 L 11.32,21.17 L 11.17,20.95 L 10.99,20.74 L 10.89,20.52 L 10.78,20.30 L 10.67,20.09 L 10.60,19.87 L 10.53,19.66 L 10.49,19.44 L 10.45,19.23 L 10.42,19.01 L 10.42,18.79 L 10.42,18.58 L 10.42,18.36 L 10.45,18.15 L 10.45,17.93 L 10.53,17.72 L 10.56,17.50 L 10.60,17.28 L 10.67,17.07 L 10.71,16.85 L 10.78,16.64 L 10.85,16.42 L 10.96,16.21 L 11.03,15.99 L 11.10,15.77 L 11.21,15.56 L 11.32,15.34 L 11.39,15.13 L 11.50,14.91 L 11.60,14.70 L 11.71,14.48 L 11.82,14.26 L 11.93,14.05 L 12.04,13.83 L 12.18,13.62 L 12.29,13.40 L 12.40,13.19 L 12.50,12.97 L 12.65,12.75 L 12.75,12.54 L 12.86,12.32 L 13.01,12.11 L 13.11,11.89 L 13.22,11.68 L 13.33,11.46 L 13.47,11.25 L 13.58,11.03 L 13.69,10.81 L 13.80,10.60 L 13.91,10.38 L 14.01,10.17 L 14.12,9.95 L 14.23,9.74 L 14.34,9.52 L 14.44,9.30 L 14.52,9.09 L 14.62,8.87 L 14.70,8.66 L 14.80,8.44 L 14.88,8.23 L 14.95,8.01 L 15.02,7.79 L 15.09,7.58 L 15.16,7.36 L 15.20,7.15 L 15.27,6.93 L 15.31,6.72 L 15.34,6.50 L 15.38,6.28 L 15.42,6.07 L 15.42,5.85 L 15.45,5.64 L 15.45,5.42 L 15.45,5.21 L 15.45,4.99 L 15.45,4.77 L 15.42,4.56 L 15.38,4.34 L 15.34,4.13 L 15.31,3.91 L 15.24,3.70 L 15.16,3.48 L 15.09,3.26 L 15.02,3.05 L 14.91,2.83 L 14.80,2.62 L 14.66,2.40 L 14.55,2.19 L 14.41,1.97 L 14.23,1.75 L 14.05,1.54 L 13.87,1.32 L 13.65,1.11 Z" fill="var(--bg)"/></svg></span>'
APP="/app"
BASE="https://app-tennismind.com"
def fr(x): return str(x).replace('.',',')

def sets_of(score,winner_is_p1=True):
    w=l=0
    for st in (score or '').split():
        try:
            a,b=[int(x.split('(')[0]) for x in st.split('-')]
        except ValueError:
            continue
        if a>b:w+=1
        else:l+=1
    return f"{w}-{l}"
def norm(sc): return ' '.join(sc.split())
def scores_block(d,state,fav):
    need=2 if d['best_of']==3 else 3
    out='<div class="sc2"><div class="sc2h">Scores les plus probables <small>meilleur des {b} sets</small></div><div class="sc2g">'.format(b=d['best_of'])
    act_sets=sets_of(d['score']) if state=='after' else None
    for sets,games,prob in d['scores']:
        cls='';tag=''
        if state=='after' and d['winner']==fav:
            if norm(games)==norm(d['score']):cls=' hit';tag='<em>Score exact trouvé</em>'
            elif sets==act_sets:cls=' near';tag='<em>Bon score en sets</em>'
        out+=f'<div class="sct{cls}"><span class="ss">{fav} {sets}</span><b>{games}</b><small>{prob} de probabilité</small>{tag}</div>'
    return out+'</div></div>'

def wx_impact(d):
    w=d['wx'];p1,p2=d['p1'],d['p2'];tr=d.get('traits') or {}
    t1=tr.get('p1') or {};t2=tr.get('p2') or {}
    if w.get('roof'): return f"Court couvert à {d['ville']} : vent, pluie et soleil sont sans effet. {p1} et {p2} jouent dans des conditions strictement identiques."
    v,t,h=w.get('vent_kmh'),w.get('temp_c'),w.get('hum_pct')
    a=b=''
    if v is not None:
        have=t1.get('ace') is not None and t2.get('ace') is not None
        if have:
            big,bt,other=(p1,t1,p2) if t1['ace']>=t2['ace'] else (p2,t2,p1)
            rt_ok=t1.get('ret') is not None and t2.get('ret') is not None
            ret,rt=((p1,t1) if t1['ret']>=t2['ret'] else (p2,t2)) if rt_ok else (other,None)
            rtxt=f" (qui gagne {rt['ret']} % des points au retour)" if rt else ""
            if v>=20: a=f"Avec {v} km/h de vent, le lancer de balle devient délicat : {big}, qui sert {fr(bt['ace'])} aces par match, perd une partie de son arme principale, et {ret}{rtxt} peut en profiter."
            elif v>=10: a=f"Un vent modéré ({v} km/h) peut perturber le lancer de balle de {big} ({fr(bt['ace'])} aces par match en moyenne), tandis que {ret} cherchera à en tirer parti."
            else: a=f"Presque pas de vent ({v} km/h) : le service de {big} ({fr(bt['ace'])} aces par match) ne sera pas gêné, ce qui conforte son avantage sur {other}."
        else:
            if v>=20: a=f"Avec {v} km/h de vent, le service et le lancer de balle deviennent difficiles pour les deux joueurs : le match peut se jouer sur la régularité."
            elif v>=10: a=f"Un vent modéré ({v} km/h) peut perturber le lancer de balle et rendre les échanges moins prévisibles."
            else: a=f"Presque pas de vent ({v} km/h) : le service ne sera pas gêné et les échanges se dérouleront normalement."
    if t is not None:
        hh=h if h is not None else 50
        if t>=28: b=f"À {t} °C, la balle vole plus vite et la fatigue s'installe : conditions favorables aux services puissants et aux points courts."
        elif t<=14: b=f"À {t} °C, l'air froid ralentit la balle et allonge les échanges : avantage au joueur le plus régulier du fond de court."
        elif hh>=70: b=f"À {t} °C avec {hh} % d'humidité, la balle devient plus lourde et les échanges s'allongent un peu."
        else: b=f"À {t} °C, la balle voyage à vitesse normale : pas de bonus particulier pour les services puissants."
    return (a+" "+b).strip()

def stats_table(d,p1,p2,surf):
    st=d.get('st') or {}
    rows=[]
    def row(a,lab,b): rows.append(f'<tr><td>{a}</td><td>{lab}</td><td>{b}</td></tr>')
    def form(f): return '<span class="form">'+''.join(f'<span class="{"w" if c in "VW" else "l"}">{c}</span>' for c in f)+'</span>'
    def pair(k,lab,fmt=lambda x:x):
        v=st.get(k)
        if v and (v[0] is not None or v[1] is not None):
            row(fmt(v[0]) if v[0] is not None else '—',lab,fmt(v[1]) if v[1] is not None else '—')
    pair('rank',d.get('rank_label','Classement'))
    pair('elo',f"Niveau TennisMind sur {surf.lower()}")
    pair('elo_all','Niveau TennisMind (toutes surfaces)')
    pair('season','Bilan sur 12 mois (V-D)')
    pair('surf',f"Victoires sur {surf.lower()} (12 mois)",lambda x:f"{x} %")
    pair('career','Bilan en carrière (V-D)')
    f=st.get('form')
    if f and f[0] and f[1]: row(form(f[0]),'Forme (5 derniers)',form(f[1]))
    pair('h2h','Face-à-face')
    pair('aces','Aces par match')
    pair('ret','Points gagnés au retour',lambda x:f"{x} %")
    pair('age','Âge',lambda x:f"{x} ans")
    pair('taille','Taille',lambda x:f"{x} cm")
    pair('main','Main')
    pair('pays','Pays')
    if not rows: return '<p class="pend">Statistiques détaillées bientôt disponibles pour ce match.</p>'
    return f'<table><caption class="sr">Statistiques comparées</caption><tr><th scope="col">{p1}</th><th scope="col"></th><th scope="col">{p2}</th></tr>'+''.join(rows)+'</table>'

def weather_section(d):
    w=d.get('wx')
    if not w: return ''
    if w.get('roof'):
        cells='<div><b>Couvert</b><small>Court couvert</small></div><div><b>Indoor</b><small>Conditions stables</small></div>'
        cells=f'<div><b>Indoor</b><small>Court couvert</small></div>'
        return f'<section class="card"><h2>Météo à {d["ville"]} le jour du match</h2><div class="wx" style="grid-template-columns:1fr">{cells}</div><p class="wxn"><strong>Impact sur le match :</strong> {wx_impact(d)}</p></section>'
    if w.get('temp_c') is None and w.get('vent_kmh') is None: return ''
    def c(v,u,l): return f'<div><b>{v}{u}</b><small>{l}</small></div>' if v not in (None,'') else ''
    cells=c(w.get('temp_c'),' °C','Température')+c(w.get('vent_kmh'),' km/h','Vent')+c(w.get('hum_pct'),' %','Humidité')+c(w.get('desc'),'','Conditions')
    return f'<section class="card"><h2>Météo à {d["ville"]} le jour du match</h2><div class="wx">{cells}</div><p class="wxn"><strong>Impact sur le match :</strong> {wx_impact(d)}</p></section>'

def scores_card(d,state,fav,p1,p2):
    need='2' if d['best_of']==3 else '3'
    out=f'<section class="card sccard"><h2>Score du match {p1} – {p2}</h2>'
    act=sets_of(d['score']) if state=='after' else None
    if state=='after':
        ac=d['actual']
        out+=f'<div class="final"><div><small>Résultat final</small><div class="fs">{d["score"]}</div><span>{d["winner"]} s\'impose {act.replace("-"," à ")}</span></div><div class="fp"><div><b>{ac["sets"]}</b><small>de probabilité pour ce résultat en sets</small></div></div></div>'
    out+='<div class="sc2g">'
    for i,(sets,games,prob) in enumerate(d['scores'],1):
        cls='';tag=''
        if state=='after' and d['winner']==fav:
            if norm(games)==norm(d['score']):cls=' hit';tag='<em>Score exact trouvé</em>'
            elif sets==act:cls=' near';tag='<em>Bon score en sets</em>'
        out+=f'<div class="sct{cls}"><div class="sl"><span class="sn">Scénario {i} · {fav} {sets}</span><b class="sg">{games}</b>{tag}</div><div class="sp">{prob}</div></div>'
    return out+'</div></section>'


def header_html():
    return f"""<header class="nav" id="nav"><a class="brand" href="/">{BRAND}<span class="brand-name">TennisMind</span></a>
<div class="nav-right"><details class="lang-dropdown"><summary class="lang-select"><span class="lang-label">Français</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></summary><div class="lang-menu"><a class="lang-option active" href="/fr/pronostics">Français</a><a class="lang-option" href="/" onclick="try{{localStorage.setItem('tennismind_lang','en')}}catch(e){{}}">English</a><a class="lang-option" href="/" onclick="try{{localStorage.setItem('tennismind_lang','es')}}catch(e){{}}">Español</a><a class="lang-option" href="/" onclick="try{{localStorage.setItem('tennismind_lang','de')}}catch(e){{}}">Deutsch</a><a class="lang-option" href="/" onclick="try{{localStorage.setItem('tennismind_lang','it')}}catch(e){{}}">Italiano</a></div></details>
<a href="{APP}" class="nav-login"><span class="chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4l6 8-6 8"/><path d="M13 4l6 8-6 8"/></svg></span><span>Connexion</span></a><a href="{APP}" class="nav-login-mobile">Se connecter</a></div></header>"""

def footer_html():
    return f"""<footer><div class="foot-wrap"><a class="brand" href="/">{BRAND}<span class="brand-name">TennisMind</span></a>
<div class="foot-links"><a href="/fr/pronostics">Pronostics</a><a href="/fr/bilan">Bilan public</a><a href="mailto:tennismindsupport@gmail.com">Support</a><a href="/legal/mentions-legales.html">Mentions légales</a><a href="/legal/cgu-cgv.html">CGU / CGV</a><a href="/legal/politique-confidentialite.html">Confidentialité</a></div>
<div class="foot-copy">© 2026 TennisMind. Toutes les analyses sont fournies à titre informatif uniquement.</div></div>
<p class="foot-note">Les pronostics TennisMind sont des estimations statistiques. Ils ne constituent ni un conseil de pari ni une garantie de résultat. Réservé aux 18 ans et plus. Jouer comporte des risques : endettement, isolement, dépendance. Appelez le 09 74 75 13 13 (appel non surtaxé).</p></footer>"""

def related_html(d):
    r=d.get('related') or []
    if not r: return ''
    return '<section class="card"><h2>Autres pronostics tennis du jour</h2>'+''.join(_row(x) for x in r)+'</section>'

def render(d,state):
    p1,p2=d['p1'],d['p2'];fav=p1 if d['pct1']>=d['pct2'] else p2;pf=max(d['pct1'],d['pct2'])
    surf={'hard':'Dur','clay':'Terre battue','grass':'Gazon'}[d['surface']];sc=f"var(--{d['surface']})"
    ds=d['date_court'].replace(' 2026','')
    title=(f"{p1} – {p2} : {d['score']}, pronostic {'juste' if d['winner']==fav else 'raté'} | TennisMind" if state=='after' else f"Pronostic {p1} – {p2} ({ds}) : {fr(pf)} % | TennisMind")
    desc=f"Pronostic {p1} – {p2} au {d['tournoi']} : {fav} favori à {fr(pf)} %. Probabilités, forme, face-à-face et analyse statistique."
    base="https://app-tennismind.com"
    url=f"{base}/fr/pronostic/{d['slug']}"
    done=state=='after'
    ev={"@type":"SportsEvent","name":f"{p1} vs {p2} – {d['tournoi']}","description":desc,"sport":"Tennis","startDate":d['iso'],
        "eventStatus":"https://schema.org/EventScheduled","eventAttendanceMode":"https://schema.org/OfflineEventAttendanceMode",
        "location":{"@type":"Place","name":d['ville'],"address":d['ville']},"competitor":[{"@type":"Person","name":p1},{"@type":"Person","name":p2}],
        "superEvent":{"@type":"SportsEvent","name":d['tournoi']},"image":f"{base}/og/{d['slug']}.png"}
    page={"@type":"WebPage","@id":url,"url":url,"name":title,"inLanguage":"fr","datePublished":d['publie_iso'],"dateModified":d['modif_iso'],
          "isPartOf":{"@type":"WebSite","name":"TennisMind","url":base},"primaryImageOfPage":f"{base}/og/{d['slug']}.png"}
    crumbs={"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":i+1,"name":n,"item":u} for i,(n,u) in enumerate([("Accueil",base+"/"),("Pronostics",base+"/fr/pronostics"),(d['tournoi'],base+"/fr/tournoi/"+d['tournoi_slug']),(f"{p1} – {p2}",url)])]}
    fq=[("Comment est calculé ce pronostic ?","TennisMind combine le niveau de chaque joueur sur la surface, la forme récente, le face-à-face, les conditions de jeu et la météo, puis compare le tout à l'historique des matchs ATP."),
        ("Peut-on se fier à ce pourcentage ?",f"Un pourcentage est une probabilité, pas une certitude : à {fr(pf)} %, le favori perd statistiquement environ un match sur {max(2,round(1/max(0.01,1-d.get('raw_pf',pf)/100)))}. Pour juger la fiabilité du modèle, le bilan public affiche chaque pronostic publié avant le match, avec son résultat réel et le taux de réussite mis à jour chaque jour.")]
    faq={"@type":"FAQPage","mainEntity":[{"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a in fq]}
    ld={"@context":"https://schema.org","@graph":[page,ev,crumbs,faq]}
    tz=d.get("tease") or ("19–15","38 %","9 – 4")
    h=f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1"><link rel="canonical" href="{url}"><link rel="alternate" hreflang="x-default" href="{url}"><link rel="alternate" hreflang="fr" href="https://app-tennismind.com/fr/pronostic/{d['slug']}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}"><meta property="og:type" content="article"><meta property="og:url" content="{url}"><meta property="og:site_name" content="TennisMind"><meta property="og:locale" content="fr_FR"><meta property="og:image" content="{base}/og/{d['slug']}.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="article:modified_time" content="{d['modif_iso']}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(title)}"><meta name="twitter:image" content="{base}/og/{d['slug']}.png"><meta name="theme-color" content="#131a16"><link rel="icon" href="/assets/favicon.png">
<script type="application/ld+json">{json.dumps(ld,ensure_ascii=False)}</script><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;700;800;900&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"><style>{CSS}</style></head><body>
{header_html()}
<main class="wrap"><article itemscope itemtype="https://schema.org/SportsEvent">
<nav class="crumb" aria-label="Fil d'Ariane"><a href="/">Accueil</a> › <a href="/fr/pronostics">Pronostics</a> › <a href="/fr/tournoi/{d['tournoi_slug']}">{d['tournoi']}</a> › {p1} – {p2}</nav>
<h1>Pronostic {p1} – {p2} : {d['tournoi']}, {d['round']}</h1>
<div class="chips"><span class="chip"><time datetime="{d['iso']}">{d['date_long']} · {d['heure']}</time></span><span class="chip">{d['tour_lbl']}</span><span class="chip surf" style="--surf:{sc}">{surf}</span><span class="chip">{d['ville']}</span></div>
<section class="card"><h2>Probabilité de victoire {p1} – {p2}</h2>
<div class="vs"><div class="pl {'fav' if fav==p1 else ''}"><img class="ph" src="{d['img1']}" alt="{p1}" width="112" height="140" loading="eager" referrerpolicy="no-referrer"><b>{p1}</b><small>{d['rank1']}</small><div class="pct">{fr(d['pct1'])} %</div></div><div class="mid">VS</div>
<div class="pl {'fav' if fav==p2 else ''}"><img class="ph" src="{d['img2']}" alt="{p2}" width="112" height="140" loading="eager" referrerpolicy="no-referrer"><b>{p2}</b><small>{d['rank2']}</small><div class="pct">{fr(d['pct2'])} %</div></div></div>
<div class="bar"><i style="width:{d['pct1']}%"></i></div><div class="legend"><span>{p1}</span><span>{p2}</span></div>"""
    if state=='after':
        ok=d['winner']==fav
        h+=f"""<div class="res"><span class="badge {'ok' if ok else 'ko'}">{'Pronostic juste' if ok else 'Pronostic raté'}</span><p class="pend" style="margin:0;flex:1 1 240px">Pronostic publié le {d['publie']} avant le match, non modifié depuis. <a href="/fr/bilan">Voir le bilan complet →</a></p></div>"""
    else:
        h+=f"""<div class="res"><div class="pend">Match prévu le {d['date_long']} à {d['heure']}. Cette page affichera le résultat réel et la justesse du pronostic juste après la rencontre.</div></div>"""
    h+="</section>"+scores_card(d,state,fav,p1,p2)
    h+=f"""<section class="card"><h2>Chiffres clés : {p1} contre {p2}</h2>{stats_table(d,p1,p2,surf)}</section>
{weather_section(d)}
<section class="card analysis"><h2>Analyse du match {p1} – {p2}</h2>{''.join(f'<p>{x}</p>' for x in d['analyse'])}</section>
<section class="card lockcard"><div class="lk-body" aria-hidden="true"><h2>Analyse détaillée {p1} – {p2}</h2>
<div class="proj"><div><b>{tz[0]}</b><small>Jeux gagnés attendus</small></div><div><b>{tz[1]}</b><small>Tie-break probable</small></div><div><b>{tz[2]}</b><small>Aces attendus</small></div></div>
<div class="fac"><div class="fh">Facteurs clés du match</div><div class="fr"><span>Service</span><i style="width:82%"></i></div><div class="fr"><span>Retour</span><i style="width:64%"></i></div><div class="fr"><span>Forme récente</span><i style="width:71%"></i></div></div>
<p class="al">Alerte : le favori perd son service en début de 2e set dans 3 matchs sur 10 sur cette surface…</p></div>
<div class="lk-over"><div class="lk-pan"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg><b>Analyse détaillée réservée aux inscrits</b><span>Projection jeu par jeu, facteurs clés et alertes avant le match.</span><a class="btn" href="{APP}">Débloquer gratuitement</a></div></div></section>
<section class="bigcta"><div class="bc-t"><span class="bc-k">Un autre match en tête ?</span><h2>Obtiens la probabilité de n'importe quel match</h2><p>Choisis deux joueurs et une surface : TennisMind calcule en quelques secondes qui est favori, avec le score projeté.</p></div><a class="btn dark" href="{APP}">Analyser un match gratuitement</a></section>
<section class="card"><h2>Questions fréquentes sur {p1} – {p2}</h2>{''.join(f'<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q,a in fq)}</section>
{related_html(d)}
</article></main>{footer_html()}</body></html>"""
    return h


# --------------------------------------------------------------------------
# Pages "liste" (hub, bilan, tournoi), sitemap, 404
# --------------------------------------------------------------------------
def page_shell(title, desc, path, body, ld=None, robots="index,follow,max-image-preview:large,max-snippet:-1"):
    url = BASE + path
    ldtag = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld else ''
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<meta name="robots" content="{robots}"><link rel="canonical" href="{url}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}"><meta property="og:type" content="website"><meta property="og:url" content="{url}"><meta property="og:site_name" content="TennisMind"><meta property="og:locale" content="fr_FR"><meta name="twitter:card" content="summary"><meta name="theme-color" content="#131a16"><link rel="icon" href="/assets/favicon.png">
{ldtag}<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;700;800;900&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"><style>{CSS}</style></head><body>
{header_html()}
<main class="wrap">{body}</main>{footer_html()}</body></html>"""


def _row(p):
    """p: dict(slug,p1,p2,pct,tournoi,time,done,ok,score,img1,img2)"""
    if p.get('done'):
        mid=f'<div class="pv {"ok" if p.get("ok") else "ko"}">{"✓" if p.get("ok") else "✗"} {html.escape(p.get("score") or "")}<small>{fr(p["pct"])} %</small></div>'
    else:
        mid=f'<div class="pv">{fr(p["pct"])} %</div>'
    sub=" · ".join(x for x in (p.get("tournoi",""),p.get("time","")) if x)
    return (f'<a class="mrow" href="/fr/pronostic/{p["slug"]}"><div class="t"><b>{html.escape(p["p1"])} – {html.escape(p["p2"])}</b>'
            f'<small>{html.escape(sub)}</small></div>'
            f'<div class="pp"><img src="{p.get("img1","")}" alt="{html.escape(p["p1"])}" width="44" height="56" loading="lazy" referrerpolicy="no-referrer">{mid}'
            f'<img src="{p.get("img2","")}" alt="{html.escape(p["p2"])}" width="44" height="56" loading="lazy" referrerpolicy="no-referrer"></div></a>')


def _grouped(rows):
    """Lignes groupées par jour, avec un intitulé de date (pas de trait)."""
    out=[];last=None
    for p in rows:
        day=p.get("day","")
        if day and day!=last:
            out.append(f'<div class="dh">{html.escape(day)}</div>');last=day
        out.append(_row(p))
    return "".join(out)


def hub_page(upcoming, recent, acc):
    crumb = '<nav class="crumb"><a href="/">Accueil</a> › Pronostics</nav>'
    h = '<h1>Pronostics tennis : probabilités de victoire ATP &amp; WTA</h1>'
    h += '<p style="color:var(--ts);margin:0 0 22px">Chaque match reçoit une probabilité de victoire et un score probable calculés par TennisMind, publiés avant la rencontre puis comparés au résultat réel.</p>'
    if acc:
        h += f'<section class="card"><h2>Taux de réussite</h2><div class="proj"><div><b>{fr(acc["pct"])} %</b><small>pronostics justes</small></div><div><b>{acc["ok"]}/{acc["total"]}</b><small>matchs vérifiés</small></div><div><a class="btn" href="/fr/bilan">Bilan public</a></div></div></section>'
    if upcoming:
        h += '<section class="card"><h2>Matchs à venir</h2>' + _grouped(upcoming) + '</section>'
    if recent:
        h += ('<details class="past"><summary class="btn ghost">Voir les matchs passés</summary>'
              '<section class="card" style="margin-top:16px"><h2>Matchs passés</h2>' + _grouped(recent) + '</section></details>')
    if not upcoming and not recent:
        h += '<section class="card"><p class="pend">Les prochains pronostics arrivent très bientôt.</p></section>'
    h += f'<section class="bigcta"><div class="bc-t"><span class="bc-k">Un autre match en tête ?</span><h2>Analyse n\'importe quel match gratuitement</h2><p>Deux joueurs, une surface : probabilité et score projeté en quelques secondes.</p></div><a class="btn dark" href="{APP}">Essayer TennisMind</a></section>'
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Pronostics tennis", "url": BASE + "/fr/pronostics", "inLanguage": "fr"}
    return page_shell("Pronostics tennis du jour : probabilités ATP & WTA | TennisMind",
                      "Pronostics tennis ATP et WTA : probabilité de victoire, score probable et résultat réel de chaque match, mis à jour tous les jours.",
                      "/fr/pronostics", crumb + h, ld)


def bilan_page(acc, rows, by_month=None):
    crumb = '<nav class="crumb"><a href="/">Accueil</a> › <a href="/fr/pronostics">Pronostics</a> › Bilan</nav>'
    h = '<h1>Bilan public des pronostics TennisMind</h1>'
    h += '<p style="color:var(--ts);margin:0 0 22px">Tous les pronostics sont publiés avant le match puis comparés au résultat réel. Aucun pronostic n\'est modifié ni supprimé après coup.</p>'
    if acc and acc["total"]:
        h += f'<section class="card"><h2>Résultat global</h2><div class="proj"><div><b>{fr(acc["pct"])} %</b><small>pronostics justes</small></div><div><b>{acc["ok"]}</b><small>justes</small></div><div><b>{acc["total"]-acc["ok"]}</b><small>ratés</small></div></div></section>'
    else:
        h += '<section class="card"><p class="pend">Le bilan s\'affichera dès les premiers matchs terminés.</p></section>'
    if rows:
        h += '<section class="card"><h2>Derniers matchs vérifiés</h2>' + _grouped(rows) + '</section>'
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": "Bilan public des pronostics tennis", "url": BASE + "/fr/bilan", "inLanguage": "fr"}
    return page_shell("Bilan public des pronostics tennis | TennisMind",
                      "Taux de réussite réel des pronostics tennis TennisMind : chaque pronostic publié avant le match, comparé au résultat.",
                      "/fr/bilan", crumb + h, ld)


def tournoi_page(name, slug, upcoming, done, acc):
    crumb = f'<nav class="crumb"><a href="/">Accueil</a> › <a href="/fr/pronostics">Pronostics</a> › {html.escape(name)}</nav>'
    h = f'<h1>Pronostics {html.escape(name)}</h1>'
    if acc and acc["total"]:
        h += f'<p style="color:var(--ts);margin:0 0 22px">Sur ce tournoi, {acc["ok"]} pronostics sur {acc["total"]} déjà vérifiés sont justes ({fr(acc["pct"])} %).</p>'
    if upcoming:
        h += '<section class="card"><h2>Matchs à venir</h2>' + _grouped(upcoming) + '</section>'
    if done:
        h += '<section class="card"><h2>Résultats</h2>' + _grouped(done) + '</section>'
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": f"Pronostics {name}", "url": f"{BASE}/fr/tournoi/{slug}", "inLanguage": "fr"}
    return page_shell(f"Pronostics {name} : probabilités et résultats | TennisMind",
                      f"Pronostics du tournoi {name} : probabilité de victoire de chaque match, score probable et résultat réel.",
                      f"/fr/tournoi/{slug}", crumb + h, ld)


def not_found_page():
    body = '<h1>Page introuvable</h1><p style="color:var(--ts)">Ce pronostic n\'existe pas ou a été retiré.</p><p><a class="btn" href="/fr/pronostics">Voir les pronostics</a></p>'
    return page_shell("Page introuvable | TennisMind", "Page introuvable.", "/fr/pronostics", body, None, "noindex,nofollow")


def sitemap_xml(entries):
    """entries = [(path, lastmod_iso, changefreq)]"""
    x = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, mod, freq in entries:
        x.append(f"<url><loc>{BASE}{path}</loc><lastmod>{mod}</lastmod><changefreq>{freq}</changefreq></url>")
    x.append('</urlset>')
    return "\n".join(x)
