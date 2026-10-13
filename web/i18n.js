// Presentation-only localization. Game state, input and certification are unchanged.
(() => {
 if(window.openrdI18n)return;
 const titles={zh:'OpenRD - Rich Diamond 开源重实现引擎',en:'OpenRD - An open-source reimplementation engine for Rich Diamond'};
 let language='zh';try{language=localStorage.getItem('openrd-language')||(/^zh/i.test(navigator.language)?'zh':'en')}catch{}
 if(!['zh','en'].includes(language))language='zh';
 const dictionary={
  'Rich Diamond 开源重实现引擎':'An open-source reimplementation engine for Rich Diamond',
  'OpenRD 来源试玩框架':'OpenRD source-data playtest','OpenRD ISO 规则资源试玩':'OpenRD ISO resource playtest',
  '从你提供的游戏或试玩数据运行，不需要另备 ISO。可玩关卡以数据自带内容为准；部分早期版本只支持基础画面。':'Runs from your game or demo data without a separate ISO. Available levels depend on your data; some early versions support basic visuals only.',
  '使用 ISO 基准游戏逻辑与关卡，可切换本地导入的资源主题。此试玩使用独立内存会话。':'Uses ISO-baseline logic and levels with locally imported resource themes. This playtest uses a separate in-memory session.',
  '关卡':'Level','资源主题':'Resource theme','全图':'Full map','已接入的本地媒体':'Imported local media','GIN 默认素材':'GIN base resources',
  '已通关，可选择其他关卡':'Completed. Choose another level.','本轮结束，点击重新开始':'Run ended. Click Restart.','点击人物同行或同列移动':'Click in the player’s row or column to move','资源图像加载失败':'Could not load resource image',
  '原始公司 Core Concepts Logo':'Original Core Concepts company logo',
  '重访钻石迷宫，探索原版的 80 个挑战与 5 个演示关卡。':'Revisit the diamond maze: 80 original challenges and 5 demonstration levels.',
  'OpenRD 是开源重实现项目，非官方作品，与 Core Concepts 及原作权利方无隶属或背书关系。原始标题、公司 Logo、图像和音视频的版权归原权利方所有，不因本项目开源而改变。项目用于学习、研究和兼容性探索。':'OpenRD is an unofficial open-source reimplementation, unaffiliated with and not endorsed by Core Concepts or the original rights holders. Original artwork, logos, audio and video remain the property of their owners. This project supports learning, research and compatibility exploration.',
  '演示与正式关卡独立解锁，两组均可从第 1 关开始。通过同组前一关，才能解锁下一关。':'Demo and full-game levels unlock separately. Both start at level 1; complete the previous level in each series to unlock the next.',
  '标准答案采用通过验证的玩家最少步解；已求出的最优步数按当前游戏模型验证。达到最优步数的玩家以大号奖杯和闪耀金字显示；相同步数保留先提交者。':'Verified player routes provide the best known answers. Certified optimal move counts apply to the current game model. Players matching them receive a large trophy and gold highlight; ties keep the first submission.',
  '开源重实现：资源格式研究、原始行为程序解析、Web 游戏界面与兼容性实现。感谢项目维护者、测试玩家及所有贡献者。':'Open-source reimplementation: resource format research, original behavior program parsing, a web game interface and compatibility work. Thanks to maintainers, players and contributors.',
  '以上原作名单来自游戏原始制作名单脚本。':'Original credits are transcribed from the game credits script.',
  '原作 · Rich Diamond / Core Concepts':'Original game · Rich Diamond / Core Concepts',
  'OpenRD 游戏地图':'OpenRD game board','游戏主菜单':'Game menu','开始游戏 / 继续挑战 →':'Play / Continue →',
  '选择关卡':'Choose level','🏆 名人堂':'🏆 Hall of Fame','名人堂':'Hall of Fame','制作人员名单':'Credits',
  '返回标题界面':'Return to title screen','← 返回标题':'← Back to title','返回标题':'Back to title',
  '游戏构思':'Game concept','程序':'Programming','市场':'Marketing','美术':'Artwork','音乐':'Music','音效':'Sound','视频':'Video','关卡设计':'Level design',
  '正常 · 50 FPS':'Normal · 50 FPS','慢 · 25 FPS':'Slow · 25 FPS','快 · 75 FPS':'Fast · 75 FPS','非常快 · 125 FPS':'Very fast · 125 FPS',
  '游戏速度':'Game speed','重新开始':'Restart','快捷存盘':'Quick save','快捷存盘 F6':'Quick save F6','读取存档':'Load save','读取存档 F9':'Load save F9',
  '音乐开关':'Toggle music','音效开关':'Toggle sound','开启音乐':'Enable music','关闭音乐':'Disable music','开启音效':'Enable sound','关闭音效':'Disable sound',
  '♫ 音乐':'♫ Music','🔊 音效':'🔊 Sound','🔇 音效':'🔇 Sound','♫ 音乐：关':'♫ Music: Off',
  '♫̸ 音乐':'♫̸ Music','音乐加载失败':'Could not load music','音效清单加载失败':'Could not load sound manifest','音效下载失败':'Could not download sound',
  '修改名字':'Edit name','方向高亮：开':'Direction highlight: On','方向高亮：关':'Direction highlight: Off',
  '切换同行 / 同列格子高亮':'Toggle row / column highlights','人物居中':'Center on player','显示整图':'Fit entire map',
  '同一位置点两次即可移动。':'Tap the same tile twice to move.','已选中目的地，再点一次此处即可移动。':'Destination selected. Tap here again to move.',
  '放大地图':'Zoom in','缩小地图':'Zoom out','关卡完成':'Level complete','挑战完成 · 祝贺你！':'Challenge complete · Congratulations!',
  '本次挑战结束':'Challenge ended','本次挑战结束，可重新开始。':'Challenge ended. You can restart.','本关运行遇到问题，请重新开始。':'A problem occurred in this level. Please restart.',
  '重试提交解法':'Retry route submission','输入高分榜名字':'Enter a leaderboard name','高分榜名字':'Leaderboard name','保存':'Save','取消':'Cancel',
  '本关高分榜 · 步数越少越靠前':'Level leaderboard · Fewer moves rank higher','通关数量排行榜':'Levels completed leaderboard',
  '下一关':'Next level','本组关卡已完成':'Series complete','行动步数':'Moves','剩余钻石':'Diamonds remaining','保护罩':'Shield',
  '红钥匙':'Red key','蓝钥匙':'Blue key','绿钥匙':'Green key','黄钥匙':'Yellow key',
  '正式关卡':'Full game','演示关卡':'Demo levels','✓ 已通关':'✓ Completed','可以挑战':'Available','🔒 通过前一关后解锁':'🔒 Complete the previous level',
  '正在读取纪录…':'Loading records…','纪录暂时无法读取':'Records are unavailable right now','尚无通关解法':'No verified route yet',
  '最优解：尚未求出':'Optimal route: Not yet known','本关尚无排名':'No rank for this level yet','填写名字后加入高分榜':'Enter a name to join the leaderboard',
  '请选择地图内的目标格':'Select a tile within the map','目标需与人物同一行或同一列':'Choose a tile in the player’s row or column',
  '原地行动 1 次，其他对象仍会行动':'Wait one move; other objects still act','已重置，点击格子开始。':'Reset. Click a tile to begin.',
  '关卡已加载，点击格子开始。':'Level loaded. Click a tile to begin.','正在提交并验证解法…':'Submitting and verifying route…',
  '名字已保存':'Name saved','本关存档已覆盖':'Save replaced for this level','已读取本关存档':'Save loaded for this level','本关还没有存档':'No save exists for this level',
  '名字需为1至24个可见字符':'Name must contain 1–24 visible characters','请先通过前一关，再挑战本关':'Complete the previous level first',
  '会话不存在或已过期，请刷新页面重新开始':'Session expired. Refresh the page to start again','请选择有效关卡':'Choose a valid level',
  '◉ 无限保护罩：开':'◉ Unlimited shield: On','◉ 无限保护罩：关':'◉ Unlimited shield: Off','DEBUG · 自由选关 / 无限保护罩':'DEBUG · Free level selection / Unlimited shield',
  '所有演示与正式关卡均可直接挑战。顶部开关可启用无限保护罩；它保留原版药剂规则，不防坠坑、溺水或熔岩。':'All demo and full-game levels are available. The unlimited shield follows potion rules and does not prevent falling, drowning or lava deaths.',
  '调试模式 · 全部 85 关可选 · 不写入普通进度或排行榜':'Debug mode · All 85 levels · Does not write normal progress or rankings',
  '调试挑战不计入进度或排行榜':'Debug play does not count toward progress or rankings',
  '重放解法':'Replay route','▶ 重放解法':'▶ Replay route','系统认证最优解':'Certified optimal route','玩家最少步解':'Best player route','暂停':'Pause','停止':'Stop','继续':'Resume',
  '读取解法…':'Loading routes…','解法读取失败':'Could not load routes','从原图重放，调试修改将清除':'Replay from the original map; debug edits will be cleared',
  '本关暂无可重放解法':'No replayable route for this level','重放已暂停':'Replay paused','重放已停止':'Replay stopped','正在停止…':'Stopping…','正在验证解法…':'Verifying route…',
  '已有重放会话，请停止后重新播放':'An existing replay is active. Stop it before restarting.',
  '☠ 击杀全部怪物':'☠ Kill all enemies','▣ 一键填坑':'▣ Fill hazards','◈ 消除全部隐藏':'◈ Reveal hidden tiles','⚿ 全部门变自动门 / 打开出口':'⚿ Open all doors / exit',
  '水填木箱，熔岩和坑填石球':'Fill water with crates; lava and pits with balls','修改目标格':'Edit target tile','底层地形':'Base terrain','上层物品 / 墙面':'Upper item / wall',
  '只修改当前调试关卡。重开关卡恢复原图。':'Changes apply only to this debug session. Restart to restore the original map.','应用修改':'Apply changes','编辑选项加载失败':'Could not load editor options',
  '当前位置':'Current position','目标位置':'Target position','地图外':'Outside map','无':'None',
  '你被压死了 · You were crushed!':'You were crushed!','你被箭刺中了 · You were stabbed!':'You were stabbed!','你被炸死了 · You blew up!':'You blew up!',
  '你被怪物吃掉了 · You were eaten!':'You were eaten!','你坠入了坑洞 · You fell!':'You fell!','你溺水了 · You drowned!':'You drowned!',
  '你被熔岩烧死了 · You were fried!':'You were fried!','你被电击了 · You were zapped!':'You were zapped!',
 };
 const patterns=[
  [/^步数 (\d+) · 钻石 (\d+) · (.+?)(?: · (\d+) 个资源未绘制)?$/,(_,moves,diamonds,outcome,missing)=>`Moves ${moves} · Diamonds ${diamonds} · ${translate(outcome)}${missing?` · ${missing} resources not drawn`:''}`],
  [/ · 映射表 (\d+)$/,(_,n)=>` · Mapping ${n}`],
  [/^已通过 (\d+) \/ (\d+) 关 · 进度保存在当前浏览器$/,(_,a,b)=>`Completed ${a} / ${b} levels · Progress saved in this browser`],
  [/^(.+) · (\d+) 步( ← 我)?$/,(_,name,n,own)=>`${name} · ${n} moves${own?' ← Me':''}`],
  [/^(.+) · (\d+) 关( ← 我)?$/,(_,name,n,own)=>`${name} · ${n} levels${own?' ← Me':''}`],
  [/^👣 (\d+) 步$/,(_,n)=>`👣 ${n} moves`],
  [/^我已通过 (\d+) 关(?: · 第 (\d+) 名)?$/,(_,n,r)=>`I completed ${n} levels${r?` · Rank ${r}`:''}`],
  [/^我的最佳排名：第 (\d+) 名$/,(_,n)=>`My best rank: ${n}`],
  [/^最优解：(\d+) 步$/,(_,n)=>`Optimal route: ${n} moves`],
  [/^已达到最优步数：(.+)，(\d+) 步$/,(_,name,n)=>`Optimal move count reached: ${name}, ${n} moves`],
  [/^目标 \((\d+), (\d+)\) · (\d+) 次行动，碰撞也计步$/,(_,x,y,n)=>`Target (${x}, ${y}) · ${n} moves; blocked moves also count`],
  [/^本关标准答案：(.+) · (\d+) 步$/,(_,name,n)=>`Best verified route: ${name} · ${n} moves`],
  [/^格子 /,()=> 'Tile '], [/^加载失败：/,()=> 'Loading failed: '], [/^音频不可用：/,()=> 'Audio unavailable: '],
  [/^解法提交失败：/,()=> 'Route submission failed: '], [/^修改目标格 /,()=> 'Edit target tile '], [/^当前：/,()=> 'Current: '],
 ];
 function translate(value){
  if(typeof value!=='string'||!value)return value;
  const trimmed=value.trim();if(dictionary[trimmed])return value.replace(trimmed,dictionary[trimmed]);
  for(const [pattern,replacement] of patterns)if(pattern.test(value))return value.replace(pattern,replacement);
  return value.replace(/(系统认证最优解|玩家最少步解)/g,m=>dictionary[m]).replace(/ · (\d+) 步/g,' · $1 moves').replace(/ · 暂无/g,' · Unavailable')
   .replace(/^(重放中|重放已暂停|重放完成)/,m=>({'重放中':'Replaying','重放已暂停':'Replay paused','重放完成':'Replay complete'}[m]))
   .replace(/^解法已提交：已更新本关最佳答案/,'Route submitted: Best verified answer updated').replace(/^解法已提交/,'Route submitted').replace(/ · 标准答案 /,' · Best verified route ');
 }
 const textSources=new WeakMap(),attributeSources=new WeakMap();let observer;
 function apply(){
  observer?.disconnect();
  document.documentElement.lang=language==='zh'?'zh-CN':'en';document.title=titles[language];
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;
  while(node=walker.nextNode()){
   if(node.parentElement?.closest('script,style,[data-language-switch]'))continue;
   const previous=textSources.get(node);let source=node.nodeValue;
   if(previous&&source===previous.rendered)source=previous.source;
   const rendered=language==='en'?translate(source):source;
   textSources.set(node,{source,rendered});if(node.nodeValue!==rendered)node.nodeValue=rendered;
  }
  for(const el of document.querySelectorAll('[title],[aria-label],[placeholder],[alt],optgroup[label]')){
   let cache=attributeSources.get(el);if(!cache){cache={};attributeSources.set(el,cache)}
   for(const name of ['title','aria-label','placeholder','label','alt']){
    if(!el.hasAttribute(name))continue;const value=el.getAttribute(name),previous=cache[name];
    const source=previous&&value===previous.rendered?previous.source:value,rendered=language==='en'?translate(source):source;
    cache[name]={source,rendered};if(value!==rendered)el.setAttribute(name,rendered);
   }
  }
  for(const b of document.querySelectorAll('[data-language-switch]')){b.textContent=language==='zh'?'English':'中文';b.setAttribute('aria-label',language==='zh'?'Switch to English':'切换为中文')}
  observer?.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder','label','alt']});
 }
 function setLanguage(next){language=next==='en'?'en':'zh';try{localStorage.setItem('openrd-language',language)}catch{}apply();document.dispatchEvent(new CustomEvent('openrd-language-change',{detail:language}))}
 function button(){const el=document.createElement('button');el.type='button';el.dataset.languageSwitch='';el.onclick=()=>setLanguage(language==='zh'?'en':'zh');return el}
 function init(){
  (document.querySelector('.controls')||document.body).prepend(button());
  const menu=document.querySelector('#menu-screen');if(menu){const b=button();b.className='menu-language';menu.prepend(b)}
  observer=new MutationObserver(apply);apply();
 }
 window.openrdI18n={get language(){return language},setLanguage,translate,refresh:apply,titles};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
