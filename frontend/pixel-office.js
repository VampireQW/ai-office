/**
 * AI办公室 Pixel Office v3 — Full rewrite inspired by pixel-agents
 * 16x32 character sprites, tile-based map, BFS pathfinding,
 * character state machine (IDLE→WALK→TYPE), multi-frame animation
 */
(function () {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────
  // TILE is now dynamic — computed per frame from canvas size
  const PX   = 2;           // sprite pixel scale (base, will scale with tile)
  const SPR_W = 16;         // sprite width in art pixels
  const SPR_H = 32;         // sprite height in art pixels
  const WALK_FRAME_DUR = 0.18;
  const TYPE_FRAME_DUR  = 0.35;

  // Character states
  const ST = { IDLE: 0, WALK: 1, TYPE: 2, READ: 3, DRINK: 4, CHAT: 5, MEET: 6 };

  // Dynamic tile size helper — computed from canvas dimensions
  function calcTile(canvasW, canvasH) {
    // Fill the canvas: pick the largest tile size that fits
    const tw = Math.floor(canvasW / MAP_COLS);
    const th = Math.floor(canvasH / MAP_ROWS);
    return Math.max(24, Math.min(tw, th)); // min 24px
  }
  function calcPX(tile) {
    // Scale sprite pixel size proportionally to tile size
    return Math.max(2, Math.round(tile / 16));
  }
  function calcWalkSpeed(tile) { return tile * 2.5; }

  // ══════════════════════════════════════════════════════════════
  // 1. SPRITE SYSTEM — pixel-perfect string template rendering
  // ══════════════════════════════════════════════════════════════
  const _cache = new Map();
  const _silhouetteCache = new Map();

  function makeSprite(tmpl, pal, scale) {
    const key = tmpl.join('') + JSON.stringify(pal) + scale;
    if (_cache.has(key)) return _cache.get(key);
    const rows = tmpl.length, cols = tmpl[0].length;
    const c = document.createElement('canvas');
    c.width = cols * scale; c.height = rows * scale;
    const x = c.getContext('2d');
    for (let r = 0; r < rows; r++)
      for (let cl = 0; cl < cols; cl++) {
        const ch = tmpl[r][cl];
        if (ch === '.') continue;
        const color = pal[ch]; if (!color) continue;
        x.fillStyle = color;
        x.fillRect(cl * scale, r * scale, scale, scale);
      }
    _cache.set(key, c); return c;
  }

  function makeSilhouette(tmpl, color, scale) {
    const key = 'sil:' + tmpl.join('') + color + scale;
    if (_silhouetteCache.has(key)) return _silhouetteCache.get(key);
    const rows = tmpl.length, cols = tmpl[0].length;
    const c = document.createElement('canvas');
    c.width = cols * scale; c.height = rows * scale;
    const x = c.getContext('2d');
    x.fillStyle = color;
    for (let r = 0; r < rows; r++)
      for (let cl = 0; cl < cols; cl++)
        if (tmpl[r][cl] !== '.') x.fillRect(cl * scale, r * scale, scale, scale);
    _silhouetteCache.set(key, c); return c;
  }

  // ══════════════════════════════════════════════════════════════
  // 2. CHARACTER SPRITES 16 wide x 32 tall — detailed pixel art
  // Legend: H=hair, h=hair-dark, S=skin, s=skin-shadow, E=eye,
  //         M=mouth, B=body, b=body-dark, A=arm, a=arm-shadow,
  //         P=pants, p=pants-dark, K=shoe, k=shoe-dark, .=transparent
  //         W=white(eye-white), O=outline, N=neck, L=belt
  // ══════════════════════════════════════════════════════════════

  // Front-facing idle (standing), frame 0
  const HUMAN_STAND = [
    '......HHHH......',  // 0  hair top
    '.....HHHHHH.....',  // 1
    '....HHHHHHHH....',  // 2
    '...HHhHHHHhHH...',  // 3  hair sides
    '...HSSSSSSSSSH..',  // 4  forehead
    '...SSSSSSSSSS...',  // 5
    '...SWESSSWES...',   // 6  eyes (W=white, E=pupil)
    '...SSSSSSSSSS...',  // 7  nose area
    '....SSMMMSS.....',  // 8  mouth
    '.....SSSSSS.....',  // 9  chin
    '......SNNS......',  // 10 neck
    '....BBBBBBBB....',  // 11 shirt top
    '...BBBBBBBBBB...',  // 12
    '..ABBBBBBBBBBa..',  // 13 arms
    '..AABBBBBBBBAA..',  // 14
    '..AA.BBBBBB.aA..',  // 15
    '..AS..BbbB..SA..',  // 16 lower shirt
    '..SS..LLLL..SS..',  // 17 belt/hands
    '......PPPP......',  // 18 pants
    '......PPPP......',  // 19
    '.....PPPPPP.....',  // 20
    '.....PP..PP.....',  // 21
    '.....PP..PP.....',  // 22
    '.....PP..PP.....',  // 23
    '.....pP..Pp.....',  // 24
    '.....PP..PP.....',  // 25
    '.....PP..PP.....',  // 26
    '.....pP..Pp.....',  // 27
    '.....KK..KK.....',  // 28 shoes
    '....KKK..KKK....',  // 29
    '....KKk..kKK....',  // 30
    '................',  // 31
  ];

  // Walk frame 1 (left foot forward)
  const HUMAN_WALK1 = [
    '......HHHH......',
    '.....HHHHHH.....',
    '....HHHHHHHH....',
    '...HHhHHHHhHH...',
    '...HSSSSSSSSSH..',
    '...SSSSSSSSSS...',
    '...SWESSSWES...',
    '...SSSSSSSSSS...',
    '....SSMMMSS.....',
    '.....SSSSSS.....',
    '......SNNS......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..ABBBBBBBBBBa..',
    '..AABBBBBBBBAA..',
    '...A.BBBBBB.A...',
    '..SS..BbbB..SS..',
    '......LLLL......',
    '......PPPP......',
    '.....PPPPPP.....',
    '....PPP..PP.....',
    '....PP...PP.....',
    '...PP....PP.....',
    '...PP.....PP....',
    '...pP.....Pp....',
    '..KK......PP....',
    '..KKk.....PP....',
    '..........pP....',
    '..........KK....',
    '..........KKK...',
    '..........KKk...',
    '................',
  ];

  // Walk frame 2 (right foot forward)
  const HUMAN_WALK2 = [
    '......HHHH......',
    '.....HHHHHH.....',
    '....HHHHHHHH....',
    '...HHhHHHHhHH...',
    '...HSSSSSSSSSH..',
    '...SSSSSSSSSS...',
    '...SWESSSWES...',
    '...SSSSSSSSSS...',
    '....SSMMMSS.....',
    '.....SSSSSS.....',
    '......SNNS......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..ABBBBBBBBBBa..',
    '..AABBBBBBBBAA..',
    '...A.BBBBBB.A...',
    '..SS..BbbB..SS..',
    '......LLLL......',
    '......PPPP......',
    '.....PPPPPP.....',
    '.....PP..PPP....',
    '.....PP...PP....',
    '.....PP....PP...',
    '....PP.....PP...',
    '....Pp.....pP...',
    '....PP......KK..',
    '....PP.....kKK..',
    '....Pp..........',
    '....KK..........',
    '...KKK..........',
    '...kKK..........',
    '................',
  ];

  // Typing (sitting at desk) — only upper body visible
  const HUMAN_TYPE1 = [
    '......HHHH......',
    '.....HHHHHH.....',
    '....HHHHHHHH....',
    '...HHhHHHHhHH...',
    '...HSSSSSSSSSH..',
    '...SSSSSSSSSS...',
    '...SWESSSWES...',
    '...SSSSSSSSSS...',
    '....SSMMMSS.....',
    '.....SSSSSS.....',
    '......SNNS......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..ABBBBBBBBBBa..',
    '.AABBBBBBBBBBA..',
    'AA..BBBBBBBB..AA',
    'SS..BBbbBBBB..SS',
    'SS...LLLLLL...SS',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
  ];

  const HUMAN_TYPE2 = [
    '......HHHH......',
    '.....HHHHHH.....',
    '....HHHHHHHH....',
    '...HHhHHHHhHH...',
    '...HSSSSSSSSSH..',
    '...SSSSSSSSSS...',
    '...SWESSSWES...',
    '...SSSSSSSSSS...',
    '....SSMMMSS.....',
    '.....SSSSSS.....',
    '......SNNS......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..ABBBBBBBBBBa..',
    '.AABBBBBBBBBBAA.',
    'AA..BBBBBBBB.AAA',
    'SS..BbbBBBBB.SS.',
    '.S...LLLLLL..S..',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
  ];

  // Robot sprites
  const ROBOT_STAND = [
    '.....OOOOOO.....',
    '....OOOOOOOO....',
    '...OOBBBBBBOO...',
    '...OBBBBBBBBBO..',
    '...OBEEOOBEEOO..',
    '...OBBBBBBBBBO..',
    '...OBBBmmBBBBO..',
    '...OBBBBBBBBBO..',
    '....OOOOOOOO....',
    '.....OBBBO......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..OBBBBBBBBBBO..',
    '..OBBBBBBBBBBOO.',
    '..OB.BBBBBB.BO..',
    '..OO.BBBBBB.OO..',
    '..OO..BBBB..OO..',
    '......LLLL......',
    '......PPPP......',
    '......PPPP......',
    '.....PPPPPP.....',
    '.....PP..PP.....',
    '.....PP..PP.....',
    '.....PP..PP.....',
    '.....PP..PP.....',
    '.....PP..PP.....',
    '.....PP..PP.....',
    '.....PP..PP.....',
    '.....KK..KK.....',
    '....KKK..KKK....',
    '....KKK..KKK....',
    '................',
  ];

  const ROBOT_TYPE1 = [
    '.....OOOOOO.....',
    '....OOOOOOOO....',
    '...OOBBBBBBOO...',
    '...OBBBBBBBBBO..',
    '...OBEEOOBEEOO..',
    '...OBBBBBBBBBO..',
    '...OBBBmmBBBBO..',
    '...OBBBBBBBBBO..',
    '....OOOOOOOO....',
    '.....OBBBO......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..OBBBBBBBBBBO..',
    '.OOBBBBBBBBBBOOO',
    'OO..BBBBBBBB..OO',
    'OO..BBBBBBBB..OO',
    'OO...BBBBB...OO.',
    '.....LLLLLL.....',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
  ];

  const ROBOT_TYPE2 = [
    '.....OOOOOO.....',
    '....OOOOOOOO....',
    '...OOBBBBBBOO...',
    '...OBBBBBBBBBO..',
    '...OBEEOOBEEOO..',
    '...OBBBBBBBBBO..',
    '...OBBBmmBBBBO..',
    '...OBBBBBBBBBO..',
    '....OOOOOOOO....',
    '.....OBBBO......',
    '....BBBBBBBB....',
    '...BBBBBBBBBB...',
    '..OBBBBBBBBBBO..',
    '.OBBBBBBBBBBBO..',
    'OO..BBBBBBBB.OOO',
    '.O..BBBBBBBB..OO',
    '.O...BBBBB...O..',
    '.....LLLLLL.....',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
  ];

  // ── Agent definitions with palettes ──
  const AGENTS = [
    // Private office (CEO & CTO) — row 2 for headroom
    { id:'ceo_01', name:'Steve', title:'CEO', robot:false, seatCol:1, seatRow:2,
      pal:{ H:'#B8793A',h:'#7E4A22', S:'#FDBCB4',s:'#E8A090', W:'#fff',E:'#1a1a2a', M:'#c04030',N:'#E8A090',
            B:'#2F6FA7',b:'#1D4E78', A:'#FDBCB4',a:'#E8A090', L:'#F0E6D2', P:'#1D2430',p:'#111722', K:'#2B2019',k:'#18100C', O:'#2C3E7B' }},
    { id:'cto_01', name:'Elon', title:'CTO', robot:false, seatCol:4, seatRow:2,
      pal:{ H:'#1a1a2a',h:'#0a0a18', S:'#C68642',s:'#A06830', W:'#fff',E:'#1a1a2a', M:'#803020',N:'#A06830',
            B:'#0E7490',b:'#0A5A70', A:'#C68642',a:'#A06830', L:'#1a1a2a', P:'#2a2a3e',p:'#1e1e2e', K:'#2a1508',k:'#1a0a04', O:'#0E7490' }},
    // Open office
    { id:'pm_01', name:'Emma', title:'PM', robot:false, seatCol:1, seatRow:7,
      pal:{ H:'#D89A4A',h:'#9B5B28', S:'#FDBCB4',s:'#E8A090', W:'#fff',E:'#1a1a2a', M:'#c04030',N:'#E8A090',
            B:'#9333EA',b:'#7928C8', A:'#FDBCB4',a:'#E8A090', L:'#1a1a2a', P:'#2a2a3e',p:'#1e1e2e', K:'#333',k:'#222', O:'#9333EA' }},
    { id:'ui_01', name:'Alex', title:'UI Designer', robot:false, seatCol:7, seatRow:7,
      pal:{ H:'#1a1200',h:'#0a0800', S:'#F1C27D',s:'#D4A860', W:'#fff',E:'#1a1a2a', M:'#c04030',N:'#D4A860',
            B:'#DB2777',b:'#B81F62', A:'#F1C27D',a:'#D4A860', L:'#1a1a2a', P:'#2a2a3e',p:'#1e1e2e', K:'#333',k:'#222', O:'#DB2777' }},
    { id:'fe_01', name:'Lucas', title:'Frontend', robot:false, seatCol:4, seatRow:7,
      pal:{ H:'#F2F2EA',h:'#BFC1C8', S:'#C68642',s:'#A06830', W:'#fff',E:'#1a1a2a', M:'#803020',N:'#A06830',
            B:'#E6EEF3',b:'#B9C8D2', A:'#C68642',a:'#A06830', L:'#1a1a2a', P:'#56606A',p:'#38424C', K:'#222',k:'#111', O:'#2563EB' }},
    { id:'be_01', name:'David', title:'Backend', robot:false, seatCol:1, seatRow:10,
      pal:{ H:'#5C3800',h:'#3A2200', S:'#FDBCB4',s:'#E8A090', W:'#fff',E:'#1a1a2a', M:'#c04030',N:'#E8A090',
            B:'#059669',b:'#047857', A:'#FDBCB4',a:'#E8A090', L:'#1a1a2a', P:'#2a2a3e',p:'#1e1e2e', K:'#222',k:'#111', O:'#059669' }},
    { id:'qa_01', name:'Sarah', title:'QA', robot:false, seatCol:4, seatRow:10,
      pal:{ H:'#CC3300',h:'#992200', S:'#F1C27D',s:'#D4A860', W:'#fff',E:'#1a1a2a', M:'#c04030',N:'#D4A860',
            B:'#DC2626',b:'#B91C1C', A:'#F1C27D',a:'#D4A860', L:'#1a1a2a', P:'#2a2a3e',p:'#1e1e2e', K:'#333',k:'#222', O:'#DC2626' }},
    { id:'aiky_main',name:'AI助手/小K', title:'总调度', robot:true, seatCol:7, seatRow:10,
      pal:{ H:'#6366f1',h:'#4f52c4', S:'#6366f1',s:'#4f52c4', W:'#1a1a2a',E:'#00eeff', M:'#00ff88',N:'#4f52c4',
            B:'#6366f1',b:'#4f52c4', A:'#6366f1',a:'#4f52c4', L:'#3a3a8a', P:'#4040aa',p:'#3030aa', K:'#333',k:'#222', O:'#818cf8' }},
    { id:'front_01', name:'Mia', title:'Reception', robot:false, npc:true, seatCol:13, seatRow:3,
      pal:{ H:'#C98538',h:'#8C4A1F', S:'#F1C27D',s:'#D4A860', W:'#fff',E:'#1a1a2a', M:'#c04030',N:'#D4A860',
            B:'#EAB8C9',b:'#C77996', A:'#F1C27D',a:'#D4A860', L:'#5E3B28', P:'#2F2A32',p:'#1F1B22', K:'#31241F',k:'#1A1110', O:'#EAB8C9' }},
  ];

  const DAILY_SPOTS = [
    { state: ST.READ,  col: 9,  row: 8,  duration: 4.5 },
    { state: ST.READ,  col: 1,  row: 4,  duration: 4.0 },
    { state: ST.DRINK, col: 10, row: 2,  duration: 3.2 },
    { state: ST.CHAT,  col: 11, row: 10, duration: 4.8 },
    { state: ST.CHAT,  col: 16, row: 12, duration: 4.8 },
    { state: ST.CHAT,  col: 13, row: 12, duration: 4.2 },
    { state: ST.MEET,  col: 11, row: 12, duration: 5.8 },
    { state: ST.MEET,  col: 12, row: 12, duration: 5.8 },
    { state: ST.MEET,  col: 13, row: 12, duration: 5.8 },
  ];

  const RECEPTION_SPOTS = [
    { state: ST.TYPE,  col: 13, row: 3, duration: 6.0 },
    { state: ST.DRINK, col: 10, row: 2, duration: 3.0 },
    { state: ST.CHAT,  col: 16, row: 3, duration: 4.0 },
  ];

  // ══════════════════════════════════════════════════════════════
  // 3. TILE MAP — office layout
  // W=wall, F=floor, D=desk, C=chair(seat)
  // ══════════════════════════════════════════════════════════════
  const MAP_COLS = 18;
  const MAP_ROWS = 14;
  // Chair(C) row is ABOVE Desk(D) row → desk Z-sorts over character legs
  // Left side: CEO/CTO private office enclosed by walls (with headroom)
  // prettier-ignore
  const TILE_MAP = [
    'WWWWWWWWWWWWWWWWWW',  // 0  top wall
    'WFFWFFWWFFFFFFFFFF',  // 1  private headroom
    'WCFWCFWWFFFFFFFFFF',  // 2  private: CEO@col1, CTO@col4 chairs
    'WDFWDFWWFFFFFFFFFF',  // 3  private: desks below chairs
    'WFFWFFWWFFFFFFFFFF',  // 4  private floor
    'WWFFWFFWFFFFFFFFFF',  // 5  wall with doors: CEO@col2-3, CTO@col5-6
    'FFFFFFFFFFFFFFFFFF',  // 6  walkway
    'FCFFCFFCFFFFFFFFFF',  // 7  open office chairs: PM@1, FE@4, UI@7
    'FDFFDFFDFFFFFFFFFF',  // 8  open office desks
    'FFFFFFFFFFFFFFFFFF',  // 9  walkway
    'FCFFCFFCFFFFFFFFFF',  // 10 chairs: BE@1, QA@4, AI office@7
    'FDFFDFFDFFFFFFFFFF',  // 11 desks
    'FFFFFFFFFFFFFFFFFF',  // 12 walkway
    'FFFFFFFFFFFFFFFFFF',  // 13 bottom
  ];

  const BLOCKED_TILES = new Set([
    // Decorative furniture and fixtures.
    '0,1','1,1','3,1','4,1',       // private-office bookshelves under windows
    '9,1','10,1','13,1',           // vending / cooler / file cabinet against window wall gaps
    '11,4','12,4','13,4',          // main reception desk
    '14,3','15,3',                 // waiting bench / visitor ledge
    '9,7','10,7','15,7','16,7',    // guest-zone bookshelves
    '12,9','14,9',                 // lounge sofas
    '13,10',                       // coffee table
    '15,10','16,10',               // right-wall TV console
    '11,11','12,11','13,11',       // meeting table
    '15,11','16,11'                // TV cabinet lower body
  ]);

  function isWalkable(col, row, allowChair = false) {
    if (row < 0 || row >= MAP_ROWS || col < 0 || col >= MAP_COLS) return false;
    if (BLOCKED_TILES.has(col + ',' + row)) return false;
    const t = TILE_MAP[row][col];
    return t === 'F' || (allowChair && t === 'C');
  }

  // ── BFS Pathfinding ──
  function findPath(fromCol, fromRow, toCol, toRow) {
    if (fromCol === toCol && fromRow === toRow) return [];
    const visited = new Set();
    const queue = [{ col: fromCol, row: fromRow, path: [] }];
    visited.add(fromCol + ',' + fromRow);
    const dirs = [[0,-1],[0,1],[-1,0],[1,0]];
    while (queue.length > 0) {
      const cur = queue.shift();
      for (const [dc, dr] of dirs) {
        const nc = cur.col + dc, nr = cur.row + dr;
        const key = nc + ',' + nr;
        if (visited.has(key)) continue;
        if (!isWalkable(nc, nr, nc === toCol && nr === toRow)) continue;
        visited.add(key);
        const newPath = [...cur.path, { col: nc, row: nr }];
        if (nc === toCol && nr === toRow) return newPath;
        queue.push({ col: nc, row: nr, path: newPath });
      }
    }
    return [];
  }

  // ══════════════════════════════════════════════════════════════
  // 4. OFFICE RENDERING — tiles, walls, furniture
  // ══════════════════════════════════════════════════════════════

  // Floor and wall colors tuned for a warmer pixel-office look.
  const WOOD_A = '#7A4A25';
  const WOOD_B = '#6B3E20';
  const TILE_A = '#D9D3C8';
  const TILE_B = '#CFC7BB';
  const CARPET_A = '#426F8E';
  const CARPET_B = '#37617E';
  const WALL_TOP = '#223149';
  const WALL_BOT = '#17243A';

  function sp(T, n) {
    return Math.max(1, Math.round(T * n / 32));
  }

  function drawPixelLine(ctx, x, y, w, h, color) {
    ctx.fillStyle = color;
    ctx.fillRect(Math.round(x), Math.round(y), Math.max(1, Math.round(w)), Math.max(1, Math.round(h)));
  }

  function drawTileMap(ctx, ox, oy, T) {
    for (let r = 0; r < MAP_ROWS; r++) {
      for (let c = 0; c < MAP_COLS; c++) {
        const x = ox + c * T, y = oy + r * T;
        const t = TILE_MAP[r][c];
        if (t === 'W') {
          const g = ctx.createLinearGradient(x, y, x, y + T);
          g.addColorStop(0, WALL_TOP); g.addColorStop(1, WALL_BOT);
          ctx.fillStyle = g; ctx.fillRect(x, y, T, T);
          drawPixelLine(ctx, x, y + T - sp(T, 4), T, sp(T, 4), '#5B4431');
          drawPixelLine(ctx, x, y + T - sp(T, 4), T, sp(T, 1), '#8A6846');
          if ((r + c) % 2 === 0) drawPixelLine(ctx, x + T - sp(T, 1), y + sp(T, 3), sp(T, 1), T - sp(T, 7), 'rgba(255,255,255,0.05)');
        } else {
          let a = WOOD_A, b = WOOD_B;
          if (r <= 5 && c >= 8) { a = TILE_A; b = TILE_B; }
          if (r >= 7 && c >= 9) { a = CARPET_A; b = CARPET_B; }
          ctx.fillStyle = (r + c) % 2 === 0 ? a : b;
          ctx.fillRect(x, y, T, T);
          if (r <= 5 && c >= 8) {
            drawPixelLine(ctx, x, y, T, sp(T, 1), 'rgba(255,255,255,0.18)');
            drawPixelLine(ctx, x, y, sp(T, 1), T, 'rgba(80,70,60,0.22)');
            drawPixelLine(ctx, x + T - sp(T, 1), y, sp(T, 1), T, 'rgba(255,255,255,0.10)');
          } else {
            drawPixelLine(ctx, x, y, T, sp(T, 1), 'rgba(255,220,160,0.08)');
            drawPixelLine(ctx, x, y, sp(T, 1), T, 'rgba(60,28,12,0.28)');
            if ((r * 17 + c * 11) % 4 === 0) {
              drawPixelLine(ctx, x + sp(T, 7), y + sp(T, 10), sp(T, 8), sp(T, 1), 'rgba(50,24,12,0.18)');
              drawPixelLine(ctx, x + sp(T, 19), y + sp(T, 22), sp(T, 6), sp(T, 1), 'rgba(255,210,140,0.08)');
            }
          }
        }
      }
    }
  }

  // Windows on wall
  function drawWindows(ctx, ox, oy, T) {
    const wallY = oy;
    const winH = T - sp(T, 8);
    const positions = [1.5, 4.5, 8.5, 11.5];
    for (const p of positions) {
      const ww = sp(T, 28);
      const wx = ox + p * T - ww / 2, wy = wallY + sp(T, 3);
      // Frame
      ctx.fillStyle = '#A8B8C8';
      ctx.fillRect(wx - sp(T, 1), wy - sp(T, 1), ww + sp(T, 2), winH + sp(T, 2));
      ctx.fillStyle = '#496071';
      ctx.fillRect(wx, wy + winH - sp(T, 2), ww, sp(T, 2));
      // Sky
      const sky = ctx.createLinearGradient(wx, wy, wx, wy + winH);
      sky.addColorStop(0, '#91D6E8'); sky.addColorStop(0.65, '#5EA4C6'); sky.addColorStop(1, '#D8EEF1');
      ctx.fillStyle = sky; ctx.fillRect(wx, wy, ww, winH);
      // Stars
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      for (let i = 0; i < 4; i++) {
        const sx = wx + 3 + ((p * 37 + i * 23) % (ww - 6)) | 0;
        const sy = wy + 2 + ((p * 13 + i * 19) % (winH - 8)) | 0;
        ctx.fillRect(sx, sy, 1, 1);
      }
      // Hills and clouds
      ctx.fillStyle = '#4A8F58';
      ctx.fillRect(wx + sp(T, 2), wy + winH - sp(T, 8), sp(T, 9), sp(T, 4));
      ctx.fillRect(wx + sp(T, 10), wy + winH - sp(T, 6), sp(T, 10), sp(T, 3));
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(wx + sp(T, 5), wy + sp(T, 5), sp(T, 5), sp(T, 2));
      ctx.fillRect(wx + sp(T, 8), wy + sp(T, 4), sp(T, 7), sp(T, 2));
      // Dividers
      ctx.fillStyle = '#6B7D8A';
      ctx.fillRect(wx + ww / 2 - sp(T, 1), wy, sp(T, 1), winH);
      ctx.fillRect(wx, wy + winH / 2, ww, sp(T, 1));
    }
  }

  // Desk + monitor + keyboard (furniture)
  function drawDesk(ctx, x, y, active, color, frame, T) {
    const dw = T + sp(T, 4), dh = Math.round(T * 0.62);
    const dx = x - sp(T, 2), dy = y - sp(T, 6);
    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(dx + sp(T, 2), dy + sp(T, 3), dw, dh);
    // Desk surface
    ctx.fillStyle = active ? '#8A5A2C' : '#6D3F1E';
    ctx.fillRect(dx, dy, dw, dh);
    ctx.fillStyle = active ? '#B2763A' : '#92592B';
    ctx.fillRect(dx, dy, dw, sp(T, 3));
    ctx.fillStyle = '#4C260E';
    ctx.fillRect(dx + sp(T, 2), dy + sp(T, 8), dw - sp(T, 4), sp(T, 1));
    ctx.fillStyle = 'rgba(255,225,170,0.16)';
    ctx.fillRect(dx + sp(T, 3), dy + sp(T, 3), dw - sp(T, 8), sp(T, 1));
    // Front
    ctx.fillStyle = '#3D2010'; ctx.fillRect(dx + sp(T, 1), dy + dh - sp(T, 5), dw - sp(T, 2), sp(T, 5));
    ctx.fillStyle = '#7B4722';
    ctx.fillRect(dx + sp(T, 4), dy + dh - sp(T, 10), sp(T, 9), sp(T, 4));
    ctx.fillRect(dx + dw - sp(T, 13), dy + dh - sp(T, 10), sp(T, 9), sp(T, 4));
    ctx.fillStyle = '#D7A361';
    ctx.fillRect(dx + sp(T, 10), dy + dh - sp(T, 8), sp(T, 1), sp(T, 1));
    ctx.fillRect(dx + dw - sp(T, 7), dy + dh - sp(T, 8), sp(T, 1), sp(T, 1));
    // Legs
    ctx.fillStyle = '#2A1505';
    ctx.fillRect(dx + sp(T, 3), dy + dh, sp(T, 2), sp(T, 4));
    ctx.fillRect(dx + dw - sp(T, 5), dy + dh, sp(T, 2), sp(T, 4));
    // Monitor
    const mw = Math.round(T * 0.42), mh = Math.round(T * 0.24);
    const mx = x + T / 2 - mw / 2, my = dy + Math.round(T * 0.05);
    ctx.fillStyle = '#1B1B22'; ctx.fillRect(mx - sp(T, 1), my - sp(T, 1), mw + sp(T, 2), mh + sp(T, 2));
    ctx.fillStyle = '#30303A'; ctx.fillRect(mx, my, mw, mh);
    // Stand
    ctx.fillStyle = '#2A2A2A';
    ctx.fillRect(x + T / 2 - sp(T, 1), my + mh, sp(T, 2), sp(T, 5));
    ctx.fillRect(x + T / 2 - sp(T, 4), my + mh + sp(T, 4), sp(T, 8), sp(T, 2));
    if (active) {
      // Screen glow
      ctx.fillStyle = '#0A1A0A'; ctx.fillRect(mx + 1, my + 1, mw - 2, mh - 2);
      ctx.globalAlpha = 0.7;
      for (let i = 0; i < 4; i++) {
        const lw = 3 + ((frame * 0.3 + i * 7) % 10) | 0;
        ctx.fillStyle = i % 2 === 0 ? color : '#88CC88';
        ctx.fillRect(mx + 2, my + 2 + i * 2.5, lw, 1);
      }
      ctx.globalAlpha = 1;
    } else {
      ctx.fillStyle = '#060608'; ctx.fillRect(mx + 1, my + 1, mw - 2, mh - 2);
      ctx.fillStyle = 'rgba(255,100,0,0.4)';
      ctx.fillRect(x + T / 2, my + mh - 2, 1, 1);
    }
    // Keyboard
    const ky = dy + Math.round(T * 0.34);
    ctx.fillStyle = '#2A2A2A';
    ctx.fillRect(x + T / 2 - sp(T, 7), ky, sp(T, 14), sp(T, 5));
    ctx.fillStyle = '#3A3A3A';
    for (let kr = 0; kr < 2; kr++)
      for (let kc = 0; kc < 5; kc++)
        ctx.fillRect(x + T / 2 - sp(T, 6) + kc * sp(T, 3), ky + sp(T, 1) + kr * sp(T, 2), sp(T, 1), sp(T, 1));
    // Desk objects
    ctx.fillStyle = '#D9C7A1';
    ctx.fillRect(dx + sp(T, 4), dy + sp(T, 4), sp(T, 7), sp(T, 5));
    ctx.fillStyle = '#E8EEF2';
    ctx.fillRect(dx + dw - sp(T, 10), dy + sp(T, 4), sp(T, 5), sp(T, 6));
    ctx.fillStyle = active ? color : '#53606C';
    ctx.fillRect(dx + dw - sp(T, 9), dy + sp(T, 5), sp(T, 3), sp(T, 1));
    ctx.fillRect(dx + dw - sp(T, 9), dy + sp(T, 7), sp(T, 2), sp(T, 1));
  }

  // Office chair — larger, proper office look
  function drawChair(ctx, x, y, T) {
    const cx = x + T / 2, cy = y + T / 2 + sp(T, 9);
    const s = T / 32; // scale factor
    ctx.fillStyle = 'rgba(0,0,0,0.22)';
    ctx.fillRect(cx - 9*s, cy + 8*s, 18*s, 5*s);
    // Seat cushion
    ctx.fillStyle = '#273241';
    ctx.fillRect(cx - 8*s, cy - 2*s, 16*s, 6*s);
    ctx.fillStyle = '#3D5268';
    ctx.fillRect(cx - 7*s, cy - 2*s, 14*s, 2*s);
    // Backrest
    ctx.fillStyle = '#2E3F53';
    ctx.fillRect(cx - 7*s, cy - 12*s, 14*s, 11*s);
    ctx.fillStyle = '#4F6B83';
    ctx.fillRect(cx - 7*s, cy - 12*s, 14*s, 2*s);
    ctx.fillStyle = '#1C2530';
    ctx.fillRect(cx - 8*s, cy - 10*s, 2*s, 10*s);
    ctx.fillRect(cx + 6*s, cy - 10*s, 2*s, 10*s);
    // Armrests
    ctx.fillStyle = '#1B2530';
    ctx.fillRect(cx - 9*s, cy - 6*s, 3*s, 8*s);
    ctx.fillRect(cx + 6*s, cy - 6*s, 3*s, 8*s);
    // Base pole
    ctx.fillStyle = '#222';
    ctx.fillRect(cx - 1*s, cy + 4*s, 2*s, 5*s);
    // Base star
    ctx.fillStyle = '#1A1A1A';
    ctx.fillRect(cx - 6*s, cy + 9*s, 4*s, 2*s);
    ctx.fillRect(cx + 2*s, cy + 9*s, 4*s, 2*s);
    ctx.fillRect(cx - 1*s, cy + 9*s, 2*s, 2*s);
    // Wheels
    ctx.fillStyle = '#111';
    ctx.fillRect(cx - 7*s, cy + 11*s, 3*s, 2*s);
    ctx.fillRect(cx + 4*s, cy + 11*s, 3*s, 2*s);
  }

  // Decorations
  function drawPlant(ctx, x, y) {
    ctx.fillStyle = '#8B5E3C'; ctx.fillRect(x + 10, y + 20, 12, 8);
    ctx.fillStyle = '#A0704A'; ctx.fillRect(x + 9, y + 18, 14, 4);
    ctx.fillStyle = '#3D2B1F'; ctx.fillRect(x + 11, y + 18, 10, 2);
    ctx.fillStyle = '#2D8A4E'; ctx.fillRect(x + 15, y + 4, 2, 14);
    const leaves = [[-3,-2],[3,-4],[-5,2],[5,0],[-2,-6],[4,-8],[0,-10],[-4,-8],[3,-6]];
    for (const [lx,ly] of leaves) {
      ctx.fillStyle = (lx+ly) % 2 ? '#2D8A4E' : '#1E6838';
      ctx.fillRect(x + 15 + lx, y + 8 + ly, 3, 2);
      ctx.fillRect(x + 16 + lx, y + 7 + ly, 1, 1);
    }
  }

  function drawWhiteboard(ctx, x, y, T) {
    ctx.fillStyle = '#888'; ctx.fillRect(x, y + 4, T - 4, T - 10);
    ctx.fillStyle = '#E8E8E0'; ctx.fillRect(x + 2, y + 6, T - 8, T - 14);
    ctx.fillStyle = '#3366CC'; ctx.fillRect(x + 5, y + 9, 12, 1);
    ctx.fillRect(x + 5, y + 12, 8, 1);
    ctx.fillStyle = '#CC3333'; ctx.fillRect(x + 5, y + 16, 15, 1);
    ctx.fillStyle = '#FFEB3B'; ctx.fillRect(x + T - 14, y + 9, 6, 6);
    ctx.fillStyle = '#4CAF50'; ctx.fillRect(x + T - 14, y + 17, 6, 6);
  }

  function drawClock(ctx, cx, cy) {
    ctx.fillStyle = '#3A3A4A';
    ctx.beginPath(); ctx.arc(cx, cy, 6, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = '#E8E8E8';
    ctx.beginPath(); ctx.arc(cx, cy, 4.5, 0, Math.PI*2); ctx.fill();
    ctx.strokeStyle = '#222'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + 2, cy - 3); ctx.stroke();
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx - 2.5, cy - 1); ctx.stroke();
    ctx.fillStyle = '#C00';
    ctx.beginPath(); ctx.arc(cx, cy, 0.8, 0, Math.PI*2); ctx.fill();
  }

  function drawBookshelf(ctx, x, y, T, cols = 2) {
    const w = T * cols - sp(T, 4), h = sp(T, 25);
    ctx.fillStyle = 'rgba(0,0,0,0.24)';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 3), w, h);
    ctx.fillStyle = '#6E421E';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#A36A34';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 2), w - sp(T, 4), sp(T, 2));
    ctx.fillStyle = '#3A1F0D';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 10), w - sp(T, 4), sp(T, 2));
    ctx.fillRect(x + sp(T, 2), y + sp(T, 19), w - sp(T, 4), sp(T, 2));
    const colors = ['#D55A4A', '#E5C755', '#4EA16F', '#4F79D8', '#E8E1CB', '#9B6AD6'];
    let idx = 0;
    for (let shelf = 0; shelf < 2; shelf++) {
      const by = y + sp(T, 4 + shelf * 9);
      for (let bx = x + sp(T, 4); bx < x + w - sp(T, 5); bx += sp(T, 4)) {
        ctx.fillStyle = colors[idx++ % colors.length];
        ctx.fillRect(bx, by + sp(T, (idx % 3)), sp(T, 2), sp(T, 5 + (idx % 3)));
      }
    }
    ctx.fillStyle = '#3A1F0D';
    ctx.fillRect(x, y + h - sp(T, 3), w, sp(T, 3));
  }

  function drawCounter(ctx, x, y, T) {
    const w = T * 2 - sp(T, 4);
    const h = sp(T, 16);
    ctx.fillStyle = '#EDE7D8';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#CDBFAD';
    ctx.fillRect(x, y + h - sp(T, 5), w, sp(T, 5));
    ctx.fillStyle = '#7C6B58';
    ctx.fillRect(x + sp(T, 3), y + h - sp(T, 9), sp(T, 13), sp(T, 4));
    ctx.fillRect(x + w - sp(T, 18), y + h - sp(T, 9), sp(T, 13), sp(T, 4));
    ctx.fillStyle = '#D68C42';
    ctx.fillRect(x + sp(T, 9), y - sp(T, 5), sp(T, 5), sp(T, 5));
    ctx.fillStyle = '#45322A';
    ctx.fillRect(x + sp(T, 10), y - sp(T, 7), sp(T, 4), sp(T, 3));
  }

  function drawReceptionDesk(ctx, x, y, T) {
    const w = T * 3 - sp(T, 6), h = sp(T, 22);
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(x + sp(T, 3), y + sp(T, 4), w, h);
    ctx.fillStyle = '#8D5A2A';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#B8793A';
    ctx.fillRect(x, y, w, sp(T, 5));
    ctx.fillStyle = '#4A2811';
    ctx.fillRect(x, y + h - sp(T, 6), w, sp(T, 6));
    ctx.fillStyle = '#6E421E';
    ctx.fillRect(x + sp(T, 6), y + sp(T, 9), sp(T, 18), sp(T, 7));
    ctx.fillRect(x + w - sp(T, 26), y + sp(T, 9), sp(T, 18), sp(T, 7));
    ctx.fillStyle = '#D9A766';
    ctx.fillRect(x + sp(T, 16), y + sp(T, 12), sp(T, 2), sp(T, 1));
    ctx.fillRect(x + w - sp(T, 16), y + sp(T, 12), sp(T, 2), sp(T, 1));
    // Sign and phone.
    ctx.fillStyle = '#F3E8C7';
    ctx.fillRect(x + sp(T, 30), y + sp(T, 8), sp(T, 26), sp(T, 7));
    ctx.fillStyle = '#6F4B24';
    ctx.font = `${sp(T, 5)}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText('INFO', x + sp(T, 43), y + sp(T, 14));
    ctx.fillStyle = '#28313A';
    ctx.fillRect(x + w - sp(T, 12), y + sp(T, 3), sp(T, 7), sp(T, 5));
    ctx.fillStyle = '#85D7E7';
    ctx.fillRect(x + w - sp(T, 10), y + sp(T, 4), sp(T, 3), sp(T, 2));
  }

  function drawVisitorBench(ctx, x, y, T) {
    const w = T * 2 - sp(T, 8);
    const h = sp(T, 18);
    ctx.fillStyle = 'rgba(0,0,0,0.22)';
    ctx.fillRect(x + sp(T, 3), y + sp(T, 4), w, h);
    ctx.fillStyle = '#C8BDAA';
    ctx.fillRect(x, y, w, sp(T, 9));
    ctx.fillStyle = '#E7DECD';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 2), w - sp(T, 4), sp(T, 3));
    ctx.fillStyle = '#786654';
    ctx.fillRect(x + sp(T, 5), y + sp(T, 9), sp(T, 3), sp(T, 8));
    ctx.fillRect(x + w - sp(T, 8), y + sp(T, 9), sp(T, 3), sp(T, 8));
    ctx.fillStyle = '#8A715B';
    ctx.fillRect(x + sp(T, 12), y + sp(T, 7), sp(T, 8), sp(T, 2));
    ctx.fillRect(x + w - sp(T, 22), y + sp(T, 7), sp(T, 8), sp(T, 2));
  }

  function drawFileCabinet(ctx, x, y, T) {
    const w = sp(T, 23), h = sp(T, 30);
    ctx.fillStyle = 'rgba(0,0,0,0.22)';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 3), w, h);
    ctx.fillStyle = '#A8B0B8';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#CBD3DA';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 2), w - sp(T, 4), sp(T, 5));
    ctx.fillStyle = '#7A838C';
    for (let i = 0; i < 3; i++) {
      const yy = y + sp(T, 8 + i * 7);
      ctx.fillRect(x + sp(T, 3), yy, w - sp(T, 6), sp(T, 5));
      ctx.fillStyle = '#DDE5EA';
      ctx.fillRect(x + sp(T, 10), yy + sp(T, 2), sp(T, 4), sp(T, 1));
      ctx.fillStyle = '#7A838C';
    }
  }

  function drawTVStand(ctx, x, y, T) {
    const w = T * 2 - sp(T, 6);
    const tvW = T + sp(T, 10);
    const tvH = sp(T, 24);
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(x + sp(T, 5), y + sp(T, 4), tvW, tvH);
    ctx.fillStyle = '#1D2430';
    ctx.fillRect(x + sp(T, 2), y, tvW, tvH);
    ctx.fillStyle = '#0E1522';
    ctx.fillRect(x + sp(T, 5), y + sp(T, 3), tvW - sp(T, 6), tvH - sp(T, 8));
    ctx.fillStyle = '#6BC3D6';
    ctx.fillRect(x + sp(T, 8), y + sp(T, 6), sp(T, 18), sp(T, 6));
    ctx.fillStyle = '#7FC36B';
    ctx.fillRect(x + sp(T, 8), y + sp(T, 15), tvW - sp(T, 18), sp(T, 4));
    ctx.fillStyle = '#F5D36D';
    ctx.fillRect(x + tvW - sp(T, 14), y + sp(T, 7), sp(T, 5), sp(T, 5));
    ctx.fillStyle = '#2A2F38';
    ctx.fillRect(x + sp(T, 17), y + tvH, sp(T, 4), sp(T, 5));
    ctx.fillStyle = '#7B4C25';
    ctx.fillRect(x, y + tvH + sp(T, 4), w, sp(T, 12));
    ctx.fillStyle = '#9F6632';
    ctx.fillRect(x, y + tvH + sp(T, 4), w, sp(T, 3));
    ctx.fillStyle = '#3B2110';
    ctx.fillRect(x + sp(T, 7), y + tvH + sp(T, 9), sp(T, 17), sp(T, 5));
    ctx.fillRect(x + w - sp(T, 24), y + tvH + sp(T, 9), sp(T, 17), sp(T, 5));
  }

  function drawSideTV(ctx, x, y, T) {
    const s = T / 32;
    const w = sp(T, 42), h = sp(T, 30);
    // Right-wall media console.
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.fillRect(x + 3*s, y + h + 7*s, w, 13*s);
    ctx.fillStyle = '#7B4C25';
    ctx.fillRect(x, y + h + 5*s, w, 12*s);
    ctx.fillStyle = '#A0632E';
    ctx.fillRect(x, y + h + 5*s, w, 3*s);
    ctx.fillStyle = '#3B2110';
    ctx.fillRect(x + 7*s, y + h + 10*s, 13*s, 5*s);
    ctx.fillRect(x + w - 20*s, y + h + 10*s, 13*s, 5*s);

    // Screen is mounted on the right side and visually faces left.
    ctx.fillStyle = '#151B25';
    ctx.fillRect(x + 5*s, y, w - 4*s, h);
    ctx.fillStyle = '#263346';
    ctx.fillRect(x + 8*s, y + 3*s, w - 10*s, h - 7*s);
    ctx.fillStyle = '#68C7D8';
    ctx.fillRect(x + 11*s, y + 7*s, 18*s, 5*s);
    ctx.fillStyle = '#9FD66B';
    ctx.fillRect(x + 11*s, y + 18*s, 24*s, 4*s);
    ctx.fillStyle = '#F2D15A';
    ctx.fillRect(x + w - 13*s, y + 8*s, 5*s, 6*s);
    ctx.fillStyle = '#0B1018';
    ctx.fillRect(x + w - 3*s, y + 2*s, 3*s, h - 4*s);
    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.fillRect(x + 8*s, y + 3*s, 2*s, h - 7*s);
  }

  function drawConferenceTable(ctx, x, y, T) {
    const w = T * 3 - sp(T, 8);
    const h = sp(T, 30);
    // Chairs around the meeting table.
    ctx.fillStyle = '#2F4050';
    ctx.fillRect(x + sp(T, 12), y - sp(T, 16), sp(T, 16), sp(T, 9));
    ctx.fillRect(x + sp(T, 44), y - sp(T, 16), sp(T, 16), sp(T, 9));
    ctx.fillRect(x + sp(T, 76), y - sp(T, 16), sp(T, 16), sp(T, 9));
    ctx.fillRect(x + sp(T, 12), y + h + sp(T, 7), sp(T, 16), sp(T, 9));
    ctx.fillRect(x + sp(T, 44), y + h + sp(T, 7), sp(T, 16), sp(T, 9));
    ctx.fillRect(x + sp(T, 76), y + h + sp(T, 7), sp(T, 16), sp(T, 9));
    ctx.fillStyle = '#50687B';
    ctx.fillRect(x + sp(T, 13), y - sp(T, 15), sp(T, 14), sp(T, 2));
    ctx.fillRect(x + sp(T, 45), y - sp(T, 15), sp(T, 14), sp(T, 2));
    ctx.fillRect(x + sp(T, 77), y - sp(T, 15), sp(T, 14), sp(T, 2));
    ctx.fillRect(x + sp(T, 13), y + h + sp(T, 8), sp(T, 14), sp(T, 2));
    ctx.fillRect(x + sp(T, 45), y + h + sp(T, 8), sp(T, 14), sp(T, 2));
    ctx.fillRect(x + sp(T, 77), y + h + sp(T, 8), sp(T, 14), sp(T, 2));

    // Table surface.
    ctx.fillStyle = 'rgba(0,0,0,0.26)';
    ctx.fillRect(x + sp(T, 3), y + sp(T, 4), w, h);
    ctx.fillStyle = '#8A5A2E';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#B4763A';
    ctx.fillRect(x, y, w, sp(T, 5));
    ctx.fillStyle = '#4A2811';
    ctx.fillRect(x, y + h - sp(T, 5), w, sp(T, 5));
    ctx.fillStyle = '#E9D9B8';
    ctx.fillRect(x + sp(T, 12), y + sp(T, 10), sp(T, 13), sp(T, 8));
    ctx.fillRect(x + sp(T, 43), y + sp(T, 8), sp(T, 15), sp(T, 10));
    ctx.fillStyle = '#6CA6D8';
    ctx.fillRect(x + sp(T, 71), y + sp(T, 10), sp(T, 12), sp(T, 8));
  }

  function drawFloorLamp(ctx, x, y, T) {
    const s = T / 32;
    ctx.fillStyle = '#2D231B';
    ctx.fillRect(x + 15*s, y + 12*s, 2*s, 22*s);
    ctx.fillRect(x + 9*s, y + 33*s, 14*s, 2*s);
    ctx.fillStyle = '#D7B35D';
    ctx.fillRect(x + 9*s, y + 5*s, 14*s, 8*s);
    ctx.fillStyle = '#F6E3A1';
    ctx.fillRect(x + 11*s, y + 6*s, 10*s, 3*s);
  }

  function drawVendingMachine(ctx, x, y, T) {
    const w = sp(T, 22), h = sp(T, 34);
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 2), w, h);
    ctx.fillStyle = '#C9D4DA';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#86B6C9';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 2), w - sp(T, 4), sp(T, 6));
    ctx.fillStyle = '#2F4350';
    ctx.fillRect(x + sp(T, 3), y + sp(T, 10), sp(T, 12), sp(T, 18));
    const cans = ['#D8584D', '#6BBE72', '#4C8BD8'];
    for (let r = 0; r < 3; r++)
      for (let c = 0; c < 2; c++) {
        ctx.fillStyle = cans[(r + c) % cans.length];
        ctx.fillRect(x + sp(T, 5 + c * 5), y + sp(T, 12 + r * 5), sp(T, 3), sp(T, 4));
      }
    ctx.fillStyle = '#1E2932';
    ctx.fillRect(x + sp(T, 16), y + sp(T, 10), sp(T, 4), sp(T, 18));
    ctx.fillStyle = '#9DE3F2';
    ctx.fillRect(x + sp(T, 17), y + sp(T, 13), sp(T, 2), sp(T, 2));
    ctx.fillStyle = '#4B5560';
    ctx.fillRect(x + sp(T, 5), y + h - sp(T, 4), w - sp(T, 10), sp(T, 2));
  }

  function drawWaterCooler(ctx, x, y, T) {
    const s = T / 32;
    ctx.fillStyle = '#DCE5EA';
    ctx.fillRect(x + 7*s, y + 12*s, 12*s, 18*s);
    ctx.fillStyle = '#6EB6D6';
    ctx.beginPath(); ctx.arc(x + 13*s, y + 9*s, 7*s, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.45)';
    ctx.fillRect(x + 10*s, y + 4*s, 4*s, 4*s);
    ctx.fillStyle = '#53606A';
    ctx.fillRect(x + 10*s, y + 19*s, 6*s, 2*s);
    ctx.fillStyle = '#26313A';
    ctx.fillRect(x + 9*s, y + 28*s, 10*s, 2*s);
  }

  function drawMeetingNook(ctx, x, y, T) {
    const w = T * 4 - sp(T, 8), h = T * 4 - sp(T, 10);
    ctx.fillStyle = 'rgba(34,56,72,0.35)';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 4), w, h);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(x + sp(T, 4), y + sp(T, 6), w - sp(T, 8), sp(T, 1));
    // Sofas
    ctx.fillStyle = '#7A4F6C';
    ctx.fillRect(x + sp(T, 4), y + sp(T, 30), sp(T, 26), sp(T, 18));
    ctx.fillRect(x + w - sp(T, 30), y + sp(T, 30), sp(T, 26), sp(T, 18));
    ctx.fillStyle = '#B58CA5';
    ctx.fillRect(x + sp(T, 6), y + sp(T, 31), sp(T, 22), sp(T, 5));
    ctx.fillRect(x + w - sp(T, 28), y + sp(T, 31), sp(T, 22), sp(T, 5));
    // Table
    const tx = x + w / 2 - sp(T, 17), ty = y + sp(T, 35);
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.fillRect(tx + sp(T, 2), ty + sp(T, 2), sp(T, 34), sp(T, 18));
    ctx.fillStyle = '#8B5B31';
    ctx.fillRect(tx, ty, sp(T, 34), sp(T, 18));
    ctx.fillStyle = '#B67A42';
    ctx.fillRect(tx + sp(T, 2), ty + sp(T, 2), sp(T, 30), sp(T, 3));
    ctx.fillStyle = '#E8E1CB';
    ctx.fillRect(tx + sp(T, 5), ty + sp(T, 6), sp(T, 8), sp(T, 6));
    ctx.fillStyle = '#6AA3D8';
    ctx.fillRect(tx + sp(T, 20), ty + sp(T, 6), sp(T, 6), sp(T, 6));
  }

  function drawFramedPicture(ctx, x, y, T) {
    const w = sp(T, 36), h = sp(T, 22);
    ctx.fillStyle = '#7A4B24';
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#E8E1CB';
    ctx.fillRect(x + sp(T, 2), y + sp(T, 2), w - sp(T, 4), h - sp(T, 4));
    ctx.fillStyle = '#6DB4D8';
    ctx.fillRect(x + sp(T, 4), y + sp(T, 4), w - sp(T, 8), h - sp(T, 8));
    ctx.fillStyle = '#F7D06A';
    ctx.fillRect(x + sp(T, 7), y + sp(T, 7), sp(T, 5), sp(T, 5));
    ctx.fillStyle = '#5BA45F';
    ctx.fillRect(x + sp(T, 5), y + h - sp(T, 8), sp(T, 12), sp(T, 4));
    ctx.fillRect(x + sp(T, 17), y + h - sp(T, 10), sp(T, 14), sp(T, 6));
  }

  function drawFineOfficeTexture(ctx, ox, oy, T) {
    for (let r = 0; r < MAP_ROWS; r++) {
      for (let c = 0; c < MAP_COLS; c++) {
        if (TILE_MAP[r][c] === 'W') continue;
        const x = ox + c * T, y = oy + r * T;
        const n = (r * 29 + c * 17) % 11;
        if (r <= 5 && c >= 8) {
          // Fine ceramic grooves in the reception area.
          drawPixelLine(ctx, x + Math.round(T * 0.5), y + 2, 1, T - 4, 'rgba(120,112,100,0.18)');
          drawPixelLine(ctx, x + 2, y + Math.round(T * 0.5), T - 4, 1, 'rgba(255,255,255,0.16)');
          drawPixelLine(ctx, x + 5 + n, y + 8, Math.max(3, Math.round(T * 0.18)), 1, 'rgba(170,160,145,0.16)');
          drawPixelLine(ctx, x + T - 12 - n, y + T - 9, Math.max(3, Math.round(T * 0.14)), 1, 'rgba(255,255,255,0.12)');
        } else if (r >= 7 && c >= 9) {
          // Subtle carpet weave in the guest zone.
          drawPixelLine(ctx, x + 2, y + Math.round(T * 0.33), T - 4, 1, 'rgba(255,255,255,0.06)');
          drawPixelLine(ctx, x + 2, y + Math.round(T * 0.66), T - 4, 1, 'rgba(0,0,0,0.08)');
          drawPixelLine(ctx, x + Math.round(T * 0.33), y + 2, 1, T - 4, 'rgba(0,0,0,0.08)');
          drawPixelLine(ctx, x + Math.round(T * 0.66), y + 2, 1, T - 4, 'rgba(255,255,255,0.05)');
          if (n % 2 === 0) drawPixelLine(ctx, x + 6 + n, y + 10, 5, 1, 'rgba(255,255,255,0.07)');
        } else {
          // Thin wood plank grain and tiny knots.
          drawPixelLine(ctx, x + 3, y + Math.round(T * 0.28), T - 6, 1, 'rgba(68,31,11,0.14)');
          drawPixelLine(ctx, x + 5, y + Math.round(T * 0.72), T - 10, 1, 'rgba(255,210,140,0.08)');
          drawPixelLine(ctx, x + Math.round(T * 0.5), y + 3, 1, T - 6, 'rgba(70,32,12,0.14)');
          if (n % 3 === 0) {
            drawPixelLine(ctx, x + 8 + n, y + 11, 6, 1, 'rgba(65,28,10,0.22)');
            drawPixelLine(ctx, x + 10 + n, y + 13, 3, 1, 'rgba(110,58,22,0.16)');
          }
        }
      }
    }
  }

  // ══════════════════════════════════════════════════════════════
  // 5. CHARACTER RENDERING + STATE MACHINE
  // ══════════════════════════════════════════════════════════════

  function getSprite(agent, state, walkFrame, typeFrame) {
    if (agent.robot) {
      if (state === ST.TYPE) return typeFrame % 2 === 0 ? ROBOT_TYPE1 : ROBOT_TYPE2;
      return ROBOT_STAND;
    }
    if (state === ST.TYPE) return typeFrame % 2 === 0 ? HUMAN_TYPE1 : HUMAN_TYPE2;
    if (state === ST.WALK) return walkFrame % 2 === 0 ? HUMAN_WALK1 : HUMAN_WALK2;
    return HUMAN_STAND;
  }

  function isDailyState(state) {
    return state === ST.READ || state === ST.DRINK || state === ST.CHAT || state === ST.MEET;
  }

  function lookFor(agent) {
    const base = {
      hair: agent.pal.H, hair2: agent.pal.h, shirt: agent.pal.B, shirt2: agent.pal.b,
      pants: agent.pal.P, pants2: agent.pal.p, skin: agent.pal.S, skin2: agent.pal.s,
      shoes: agent.pal.K, accent: agent.pal.B, style: 'short'
    };
    const looks = {
      ceo_01: { hair:'#B8793A', hair2:'#7A481E', shirt:'#2F6FA7', shirt2:'#1D4E78', pants:'#1F2937', accent:'#E8EEF4', tie:'#D84B3C', style:'side' },
      pm_01: { hair:'#D89A4A', hair2:'#9B5B28', shirt:'#242226', shirt2:'#111114', pants:'#25252D', accent:'#F1C232', style:'braids' },
      cto_01: { hair:'#111118', hair2:'#050508', shirt:'#F97316', shirt2:'#C94F13', pants:'#263040', accent:'#FFD166', style:'curly' },
      ui_01: { hair:'#171820', hair2:'#07080D', shirt:'#C92D45', shirt2:'#8E1F35', pants:'#2B2B35', accent:'#F3E7E7', style:'asymBob' },
      fe_01: { hair:'#F4F4ED', hair2:'#C8CAD0', shirt:'#D9E4EA', shirt2:'#91A9B8', pants:'#636C75', accent:'#2F8FB8', style:'puffy' },
      be_01: { hair:'#6F3D16', hair2:'#3E210B', shirt:'#059669', shirt2:'#047857', pants:'#2F3540', accent:'#EAEFDF', style:'messy' },
      qa_01: { hair:'#E43B18', hair2:'#8F1A0B', shirt:'#DC2626', shirt2:'#B91C1C', pants:'#202735', accent:'#FFD166', style:'shortFlip' },
      front_01: { hair:'#D99845', hair2:'#A85D26', shirt:'#EAB8C9', shirt2:'#C77996', pants:'#2F2A32', accent:'#F7DCE6', style:'long' },
    };
    return { ...base, ...(looks[agent.id] || {}) };
  }

  function drawHumanCharacterV2(ctx, agent, ch, frame, ox, oy, px) {
    const look = lookFor(agent);
    const u = Math.max(1, Math.round(px * 0.7));
    const W = 24, H = 40;
    const w = W * u, h = H * u;
    let yOff = 0;
    if (ch.state === ST.IDLE || isDailyState(ch.state)) yOff = Math.sin(frame * 0.05 + agent.seatCol) * u;
    const sittingOffset = ch.state === ST.TYPE ? u * 6 : 0;
    const sx = Math.round(ox + ch.x - w / 2);
    const sy = Math.round(oy + ch.y - h + sittingOffset + yOff);
    const phase = ch.walkFrame % 2;
    const step = ch.state === ST.WALK ? (phase === 0 ? -2 : 2) : 0;
    const typeTap = ch.state === ST.TYPE ? (ch.typeFrame % 2) : 0;

    if (ch.state !== ST.TYPE) {
      ctx.fillStyle = 'rgba(0,0,0,0.26)';
      ctx.beginPath();
      ctx.ellipse(ox + ch.x, oy + ch.y + 2, Math.max(8, 7 * u), Math.max(3, 2.5 * u), 0, 0, Math.PI * 2);
      ctx.fill();
    }

    const p = (x, y, ww, hh, color) => drawPixelLine(ctx, sx + x * u, sy + y * u, ww * u, hh * u, color);

    // Outline and legs.
    p(7, 25, 4, 11 + Math.max(step, 0), '#111217');
    p(13, 25, 4, 11 + Math.max(-step, 0), '#111217');
    p(8, 25, 3, 10 + Math.max(step, 0), look.pants);
    p(13, 25, 3, 10 + Math.max(-step, 0), look.pants2);
    p(6, 35 + Math.max(step, 0), 5, 2, '#111114');
    p(13, 35 + Math.max(-step, 0), 5, 2, '#111114');
    p(7, 36 + Math.max(step, 0), 4, 1, look.shoes);
    p(14, 36 + Math.max(-step, 0), 4, 1, look.shoes);

    // Body outline and clothes.
    p(6, 16, 12, 12, '#111217');
    p(7, 17, 10, 10, look.shirt);
    p(7, 17, 10, 2, look.accent);
    p(7, 25, 10, 2, look.shirt2);
    p(11, 17, 2, 10, look.tie || look.accent);
    p(5, 18 + typeTap, 3, 9, '#111217');
    p(16, 18 + (typeTap ? 0 : 1), 3, 9, '#111217');
    p(5, 19 + typeTap, 2, 7, look.skin);
    p(17, 19 + (typeTap ? 0 : 1), 2, 7, look.skin);
    p(4, 25 + typeTap, 3, 2, look.skin2);
    p(17, 25 + (typeTap ? 0 : 1), 3, 2, look.skin2);

    // Neck, head outline and face.
    p(10, 13, 4, 4, '#111217');
    p(10, 14, 4, 3, look.skin2);
    p(6, 4, 12, 12, '#111217');
    p(7, 5, 10, 10, look.skin);
    p(8, 11, 8, 4, look.skin2);
    p(7, 9, 1, 4, look.skin2);
    p(16, 9, 1, 4, look.skin2);

    // Hair styles.
    if (look.style === 'long') {
      p(5, 3, 14, 4, look.hair);
      p(4, 6, 4, 12, look.hair);
      p(16, 6, 4, 12, look.hair2);
      for (let i = 0; i < 5; i++) p(7 + i * 2, 4 + i, 1, 12, i % 2 ? look.hair2 : '#E1A75A');
    } else if (look.style === 'puffy') {
      p(6, 2, 12, 5, look.hair);
      p(5, 5, 4, 6, look.hair2);
      p(15, 5, 4, 6, look.hair);
      p(8, 1, 7, 3, '#FFFFFF');
    } else if (look.style === 'bob') {
      p(5, 3, 14, 5, look.hair);
      p(5, 7, 3, 8, look.hair2);
      p(16, 7, 3, 8, look.hair2);
      p(8, 4, 8, 2, '#2F3038');
    } else if (look.style === 'curly') {
      p(6, 2, 4, 4, look.hair);
      p(10, 1, 4, 5, look.hair2);
      p(14, 3, 4, 4, look.hair);
      p(5, 5, 3, 4, look.hair2);
    } else if (look.style === 'messy') {
      p(7, 1, 4, 5, look.hair);
      p(11, 2, 5, 4, look.hair2);
      p(5, 4, 4, 4, look.hair);
      p(15, 5, 3, 3, look.hair2);
    } else {
      p(6, 2, 12, 5, look.hair);
      p(5, 5, 4, 4, look.hair2);
      p(14, 4, 4, 4, look.hair);
    }

    // Face: visible expression with small pixels.
    p(8, 9, 3, 2, '#F7F7F7');
    p(14, 9, 3, 2, '#F7F7F7');
    p(9, 9, 1, 2, '#171722');
    p(15, 9, 1, 2, '#171722');
    p(8, 8, 3, 1, look.hair2);
    p(14, 8, 3, 1, look.hair2);
    p(12, 11, 1, 2, look.skin2);
    p(9, 12, 2, 1, 'rgba(255,122,112,0.45)');
    p(15, 12, 2, 1, 'rgba(255,122,112,0.40)');
    const speaking = ch.state === ST.CHAT;
    p(10, 14, speaking ? 4 : 5, 1, '#8D221F');
    if (!speaking) p(11, 13, 3, 1, '#F6D0C5');

    if (agent.id === 'ceo_01' || agent.id === 'ui_01') {
      p(8, 9, 3, 1, '#111217'); p(14, 9, 3, 1, '#111217'); p(11, 9, 3, 1, '#111217');
      p(9, 10, 1, 1, 'rgba(255,255,255,0.75)'); p(15, 10, 1, 1, 'rgba(255,255,255,0.75)');
    }
    if (agent.id === 'cto_01' || agent.id === 'fe_01') {
      p(4, 12, 3, 7, '#12151B');
      p(17, 12, 3, 7, '#12151B');
      p(18, 10, 1, 7, look.accent);
    }

    // Typing hands and activity props use the same smaller pixel grid.
    if (ch.state === ST.TYPE) {
      p(6, 24 + typeTap, 4, 1, 'rgba(255,255,255,0.45)');
      p(14, 24 + (typeTap ? 0 : 1), 4, 1, 'rgba(255,255,255,0.45)');
    }

    drawActivityPropV2(ctx, agent, ch, sx, sy, u, frame, ox, oy);
  }

  function charUnit() {
    return 1.5;
  }

  function characterVisualHeight(agent) {
    return agent && agent.id === 'aiky_main' ? 52 * charUnit() : 52 * charUnit();
  }

  function characterTagHeight(agent, ch) {
    if (ch && (ch.state === ST.TYPE || ch.state === ST.MEET)) return 34 * charUnit();
    return characterVisualHeight(agent);
  }

  function sittingSpriteOffset(ch, T) {
    if (ch.state === ST.MEET) return Math.round(T * 0.28 + 10);
    if (ch.state === ST.TYPE) return Math.round(T * 0.65 + 20);
    return 0;
  }

  function meetingSeatVisualOffset(ch, T) {
    if (ch.state !== ST.MEET) return { x: 0, y: 0 };
    return { x: Math.round(T * 0.26), y: Math.round(-T * 0.08) };
  }

  function drawHumanCharacterV3(ctx, agent, ch, frame, ox, oy, T) {
    const look = lookFor(agent);
    const u = charUnit();
    const W = 32, H = 52;
    const w = W * u, h = H * u;
    const sitting = ch.state === ST.TYPE || ch.state === ST.MEET;
    let yOff = 0;
    if (!sitting && (ch.state === ST.IDLE || isDailyState(ch.state))) yOff = Math.sin(frame * 0.05 + agent.seatCol) * 1.2;
    const sittingOffset = sittingSpriteOffset(ch, T);
    const meetOffset = meetingSeatVisualOffset(ch, T);
    const renderX = ch.x + meetOffset.x;
    const renderY = ch.y + meetOffset.y;
    const sx = Math.round(ox + renderX - w / 2);
    const sy = Math.round(oy + renderY - h + sittingOffset + yOff);
    const phase = ch.walkFrame % 2;
    const legSwing = ch.state === ST.WALK ? (phase === 0 ? -2 : 2) : 0;
    const tap = ch.state === ST.TYPE ? (ch.typeFrame % 2) : 0;
    const speaking = ch.state === ST.CHAT;

    if (!sitting) {
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.beginPath();
      ctx.ellipse(ox + renderX, oy + renderY + 2, 9, 3.5, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    const p = (x, y, ww, hh, color) => drawPixelLine(ctx, sx + x * u, sy + y * u, ww * u, hh * u, color);
    const outline = 'rgba(18,20,27,0.62)';
    const hairEdge = 'rgba(48,36,28,0.55)';
    const skinHi = '#FFD8C7';

    // Legs and shoes. Work mode has a compact seated pose.
    if (sitting) {
      p(9, 32, 15, 5, outline);
      p(10, 32, 6, 4, look.pants);
      p(17, 32, 6, 4, look.pants2);
      p(8, 36, 7, 3, outline);
      p(19, 36, 7, 3, outline);
      p(9, 37, 5, 1, look.shoes);
      p(20, 37, 5, 1, look.shoes);
    } else {
      p(10, 32, 5, 14 + Math.max(legSwing, 0), outline);
      p(18, 32, 5, 14 + Math.max(-legSwing, 0), outline);
      p(11, 32, 3, 13 + Math.max(legSwing, 0), look.pants);
      p(19, 32, 3, 13 + Math.max(-legSwing, 0), look.pants2);
      p(9, 46 + Math.max(legSwing, 0), 6, 3, outline);
      p(18, 46 + Math.max(-legSwing, 0), 7, 3, outline);
      p(10, 47 + Math.max(legSwing, 0), 5, 1, look.shoes);
      p(19, 47 + Math.max(-legSwing, 0), 5, 1, look.shoes);
    }

    // Torso and arms.
    p(8, 22, 16, 13, outline);
    p(9, 23, 14, 11, look.shirt);
    p(9, 23, 14, 2, look.accent);
    p(9, 33, 14, 2, look.shirt2);
    if (look.tie) {
      p(15, 23, 2, 8, look.tie);
      p(14, 29, 4, 3, look.tie);
    } else {
      p(15, 23, 2, 8, 'rgba(255,255,255,0.28)');
    }
    p(6, 23 + tap, 4, 11, outline);
    p(23, 23 + (tap ? 0 : 1), 4, 11, outline);
    p(7, 24 + tap, 2, 9, look.skin);
    p(24, 24 + (tap ? 0 : 1), 2, 9, look.skin);
    p(6, 33 + tap, 4, 2, look.skin2);
    p(23, 33 + (tap ? 0 : 1), 4, 2, look.skin2);

    // Neck and head.
    p(14, 18, 5, 5, outline);
    p(14, 19, 5, 4, look.skin2);
    p(8, 6, 17, 15, outline);
    p(9, 7, 15, 14, look.skin);
    p(10, 17, 13, 4, look.skin2);
    p(9, 11, 1, 6, look.skin2);
    p(23, 11, 1, 6, look.skin2);
    p(11, 8, 10, 2, skinHi);

    // Hair with softer outlines, style-specific.
    if (look.style === 'braids') {
      p(7, 4, 19, 5, hairEdge);
      p(6, 8, 4, 14, hairEdge);
      p(23, 8, 4, 14, hairEdge);
      p(8, 5, 17, 4, look.hair);
      p(7, 9, 3, 13, look.hair);
      p(23, 9, 3, 13, look.hair2);
      for (let i = 0; i < 5; i++) {
        p(6 + (i % 2), 11 + i * 2, 3, 1, i % 2 ? look.hair2 : '#E8B663');
        p(24 - (i % 2), 11 + i * 2, 3, 1, i % 2 ? '#E8B663' : look.hair2);
      }
      p(10, 6, 5, 2, '#F0BE67');
      p(16, 6, 5, 2, look.hair2);
    } else if (look.style === 'asymBob') {
      p(7, 4, 19, 6, hairEdge);
      p(6, 9, 5, 9, hairEdge);
      p(21, 9, 6, 13, hairEdge);
      p(8, 5, 17, 5, look.hair);
      p(7, 10, 4, 8, look.hair2);
      p(21, 9, 5, 12, look.hair);
      p(18, 6, 7, 3, look.hair2);
      p(9, 9, 5, 1, '#2A2B35');
    } else if (look.style === 'shortFlip') {
      p(7, 4, 18, 5, hairEdge);
      p(6, 8, 5, 6, hairEdge);
      p(21, 8, 5, 6, hairEdge);
      p(8, 5, 16, 4, look.hair);
      p(7, 9, 4, 5, look.hair2);
      p(21, 9, 4, 5, look.hair);
      p(6, 13, 4, 3, look.hair);
      p(23, 12, 4, 3, look.hair2);
      p(11, 4, 8, 2, '#FF6A2E');
    } else if (look.style === 'long') {
      p(7, 4, 19, 5, hairEdge);
      p(6, 8, 5, 17, hairEdge);
      p(22, 8, 5, 17, hairEdge);
      p(8, 5, 17, 4, look.hair);
      p(7, 9, 4, 16, look.hair);
      p(22, 9, 4, 16, look.hair2);
      p(10, 7, 4, 2, look.hair2);
      p(15, 7, 4, 2, look.hair);
      p(7, 12, 1, 12, '#E5A85A');
      p(24, 12, 1, 12, 'rgba(90,52,24,0.55)');
    } else if (look.style === 'puffy') {
      p(7, 3, 19, 7, hairEdge);
      p(6, 8, 5, 8, hairEdge);
      p(22, 8, 5, 8, hairEdge);
      p(8, 4, 17, 6, look.hair);
      p(7, 9, 5, 7, look.hair2);
      p(21, 9, 5, 7, look.hair);
      p(11, 3, 10, 3, '#FFFFFF');
    } else if (look.style === 'bob') {
      p(7, 4, 19, 6, hairEdge);
      p(7, 9, 5, 11, hairEdge);
      p(21, 9, 5, 11, hairEdge);
      p(8, 5, 17, 5, look.hair);
      p(8, 10, 4, 10, look.hair2);
      p(21, 10, 4, 10, look.hair2);
    } else if (look.style === 'curly') {
      const curls = [[8,4,5,5],[13,3,5,6],[18,4,5,5],[6,8,5,5],[22,8,4,5]];
      for (const [x,y,ww,hh] of curls) p(x - 1, y - 1, ww + 2, hh + 2, hairEdge);
      curls.forEach(([x,y,ww,hh], i) => p(x, y, ww, hh, i % 2 ? look.hair2 : look.hair));
    } else if (look.style === 'messy') {
      p(8, 3, 6, 7, hairEdge); p(14, 4, 7, 6, hairEdge); p(20, 6, 5, 5, hairEdge); p(6, 8, 5, 5, hairEdge);
      p(9, 4, 5, 6, look.hair); p(15, 5, 6, 5, look.hair2); p(20, 7, 4, 4, look.hair); p(7, 9, 4, 4, look.hair);
    } else {
      p(7, 4, 19, 6, hairEdge);
      p(7, 9, 5, 5, hairEdge);
      p(21, 9, 5, 5, hairEdge);
      p(8, 5, 17, 5, look.hair);
      p(8, 10, 5, 4, look.hair2);
      p(20, 9, 5, 4, look.hair);
    }

    // Eyes and expression: larger face area, smaller pixels.
    p(11, 12, 5, 3, '#F7F8FA');
    p(18, 12, 5, 3, '#F7F8FA');
    p(13, 12, 2, 3, '#1C1E28');
    p(20, 12, 2, 3, '#1C1E28');
    p(13, 12, 1, 1, '#FFFFFF');
    p(20, 12, 1, 1, '#FFFFFF');
    p(11, 10, 5, 1, look.hair2);
    p(18, 10, 5, 1, look.hair2);
    p(16, 15, 1, 3, look.skin2);
    p(11, 17, 3, 1, 'rgba(255,126,118,0.42)');
    p(20, 17, 3, 1, 'rgba(255,126,118,0.38)');
    if (speaking) {
      p(14, 19, 5, 2, '#7A1E1D');
      p(15, 20, 3, 1, '#F2B4A8');
    } else {
      p(14, 19, 5, 1, '#8D221F');
      p(15, 18, 3, 1, '#F5CCC1');
    }

    if (agent.id === 'ceo_01' || agent.id === 'ui_01') {
      p(11, 12, 5, 1, '#242735');
      p(18, 12, 5, 1, '#242735');
      p(16, 12, 2, 1, '#242735');
      p(12, 13, 1, 1, 'rgba(255,255,255,0.7)');
      p(19, 13, 1, 1, 'rgba(255,255,255,0.7)');
    }
    if (agent.id === 'cto_01' || agent.id === 'fe_01') {
      p(5, 18, 4, 10, 'rgba(22,24,32,0.72)');
      p(24, 18, 4, 10, 'rgba(22,24,32,0.72)');
      p(26, 14, 1, 10, look.accent);
    }

    if (agent.id === 'front_01') {
      p(9, 23, 14, 3, '#F7DCE6');
      p(10, 26, 12, 5, '#EAB8C9');
      p(11, 35, 4, 11, look.pants);
      p(18, 35, 4, 11, look.pants);
    }

    if (ch.state === ST.TYPE) {
      p(8, 32 + tap, 5, 1, 'rgba(255,255,255,0.45)');
      p(20, 32 + (tap ? 0 : 1), 5, 1, 'rgba(255,255,255,0.45)');
    }

    drawActivityPropV3(ctx, agent, ch, sx, sy, u, frame, ox, oy);
  }

  function drawActivityPropV3(ctx, agent, ch, sx, sy, u, frame, ox, oy) {
    const p = (x, y, w, h, color) => drawPixelLine(ctx, sx + x * u, sy + y * u, w * u, h * u, color);
    const bob = Math.round(Math.sin(frame * 0.08 + ch.tileCol) * u);
    if (ch.state === ST.READ) {
      p(7, 27, 8, 7, '#F4E7C6');
      p(16, 27, 8, 7, '#F4E7C6');
      p(15, 27, 1, 7, '#A87334');
      p(8, 29, 5, 1, '#6E7FA8');
      p(18, 30, 5, 1, '#6E7FA8');
    } else if (ch.state === ST.DRINK) {
      p(23, 23, 4, 6, '#F1F5F2');
      p(24, 22, 2, 1, '#FFFFFF');
      p(27, 25, 1, 2, '#F1F5F2');
      ctx.globalAlpha = 0.45;
      p(24, 18 + (bob > 0 ? 1 : 0), 1, 2, '#DDEFF4');
      p(25, 17 + (bob > 0 ? 1 : 0), 1, 2, '#DDEFF4');
      ctx.globalAlpha = 1;
    } else if (ch.state === ST.CHAT) {
      const propOffset = meetingSeatVisualOffset(ch, 32 * u);
      const propX = ch.x + propOffset.x;
      const propY = ch.y + propOffset.y;
      const bx = ox + propX + 12;
      const by = oy + propY - 58 * u + bob;
      ctx.fillStyle = 'rgba(255,255,255,0.94)';
      roundRect(ctx, bx, by, 24, 14, 4); ctx.fill();
      ctx.fillStyle = agent.pal.B;
      ctx.fillRect(bx + 5, by + 6, 3, 3);
      ctx.fillRect(bx + 11, by + 6, 3, 3);
      ctx.fillRect(bx + 17, by + 6, 3, 3);
    } else if (ch.state === ST.MEET) {
      p(8, 31, 5, 1, 'rgba(255,255,255,0.45)');
      p(19, 31, 5, 1, 'rgba(255,255,255,0.45)');
      p(13, 27, 7, 4, '#F4E7C6');
      p(14, 28, 5, 1, '#6E7FA8');
    }
  }

  function drawAikyCharacterV3(ctx, agent, ch, frame, ox, oy, T) {
    const u = charUnit();
    const W = 32, H = 52;
    const w = W * u, h = H * u;
    const sitting = ch.state === ST.TYPE || ch.state === ST.MEET;
    let yOff = 0;
    if (!sitting && (ch.state === ST.IDLE || isDailyState(ch.state))) yOff = Math.sin(frame * 0.05 + 0.8) * 1.3;
    const sittingOffset = sittingSpriteOffset(ch, T);
    const meetOffset = meetingSeatVisualOffset(ch, T);
    const renderX = ch.x + meetOffset.x;
    const renderY = ch.y + meetOffset.y;
    const sx = Math.round(ox + renderX - w / 2);
    const sy = Math.round(oy + renderY - h + sittingOffset + yOff);
    const phase = ch.walkFrame % 2;
    const legSwing = ch.state === ST.WALK ? (phase === 0 ? -2 : 2) : 0;
    const tap = ch.state === ST.TYPE ? (ch.typeFrame % 2) : 0;
    const pulse = 0.55 + 0.35 * Math.sin(frame * 0.08);
    const p = (x, y, ww, hh, color) => drawPixelLine(ctx, sx + x * u, sy + y * u, ww * u, hh * u, color);

    if (!sitting) {
      ctx.fillStyle = 'rgba(0,0,0,0.28)';
      ctx.beginPath();
      ctx.ellipse(ox + renderX, oy + renderY + 2, 10 * u, 3.5 * u, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    const outline = '#10121A';
    const shell = '#6C6FF5';
    const shell2 = '#474CD0';
    const glow = '#00E8FF';
    const green = '#00FF88';

    // Legs and shoes.
    if (sitting) {
      p(9, 32, 15, 5, outline);
      p(10, 33, 6, 3, '#3035A8');
      p(17, 33, 6, 3, '#262B8E');
      p(8, 36, 7, 3, outline);
      p(19, 36, 7, 3, outline);
    } else {
      p(10, 32, 5, 14 + Math.max(legSwing, 0), outline);
      p(18, 32, 5, 14 + Math.max(-legSwing, 0), outline);
      p(11, 33, 3, 12 + Math.max(legSwing, 0), '#3035A8');
      p(19, 33, 3, 12 + Math.max(-legSwing, 0), '#262B8E');
      p(9, 46 + Math.max(legSwing, 0), 6, 3, outline);
      p(18, 46 + Math.max(-legSwing, 0), 7, 3, outline);
    }

    // Body and arms.
    p(7, 21, 18, 15, outline);
    p(8, 22, 16, 13, shell);
    p(9, 24, 14, 4, '#3E44D7');
    p(10, 28, 12, 3, green);
    p(10, 32, 12, 2, shell2);
    p(5, 23 + tap, 4, 12, outline);
    p(23, 23 + (tap ? 0 : 1), 4, 12, outline);
    p(6, 24 + tap, 2, 9, shell);
    p(24, 24 + (tap ? 0 : 1), 2, 9, shell);
    p(5, 34 + tap, 4, 2, '#8387FF');
    p(23, 34 + (tap ? 0 : 1), 4, 2, '#8387FF');

    // Head with antenna.
    p(15, 1, 2, 5, outline);
    p(15, 0, 2, 2, '#B8C7FF');
    p(9, 5, 15, 15, outline);
    p(10, 6, 13, 13, shell);
    p(11, 8, 11, 3, '#9CA3FF');
    p(11, 13, 11, 3, shell2);
    p(8, 10, 2, 6, '#B8C7FF');
    p(23, 10, 2, 6, '#B8C7FF');

    ctx.globalAlpha = pulse;
    p(12, 11, 4, 2, glow);
    p(18, 11, 4, 2, glow);
    p(13, 17, 7, 1, green);
    ctx.globalAlpha = 1;
    if (ch.state === ST.CHAT) {
      p(14, 16, 5, 2, green);
    }

    // Small panels and typing sparks.
    p(12, 24, 8, 1, 'rgba(255,255,255,0.45)');
    p(12, 26, 4, 1, '#00E8FF');
    p(17, 26, 4, 1, '#00FF88');
    if (ch.state === ST.TYPE) {
      p(7, 33 + tap, 5, 1, 'rgba(255,255,255,0.55)');
      p(20, 33 + (tap ? 0 : 1), 5, 1, 'rgba(255,255,255,0.55)');
    }

    drawActivityPropV3(ctx, agent, ch, sx, sy, u, frame, ox, oy);
  }

  function drawActivityPropV2(ctx, agent, ch, sx, sy, u, frame, ox, oy) {
    const p = (x, y, w, h, color) => drawPixelLine(ctx, sx + x * u, sy + y * u, w * u, h * u, color);
    const bob = Math.round(Math.sin(frame * 0.08 + ch.tileCol) * u);
    if (ch.state === ST.READ) {
      p(5, 20, 6, 6, '#F4E7C6');
      p(12, 20, 6, 6, '#F4E7C6');
      p(11, 20, 1, 6, '#A87334');
      p(6, 22, 4, 1, '#6E7FA8');
      p(13, 23, 4, 1, '#6E7FA8');
    } else if (ch.state === ST.DRINK) {
      p(17, 18, 3, 5, '#F1F5F2');
      p(18, 17, 1, 1, '#FFFFFF');
      p(20, 19, 1, 2, '#F1F5F2');
      ctx.globalAlpha = 0.45;
      p(18, 14 + (bob > 0 ? 1 : 0), 1, 2, '#DDEFF4');
      p(19, 13 + (bob > 0 ? 1 : 0), 1, 2, '#DDEFF4');
      ctx.globalAlpha = 1;
    } else if (ch.state === ST.CHAT) {
      const bx = ox + ch.x + 12;
      const by = oy + ch.y - 42 * u - 14 + bob;
      ctx.fillStyle = 'rgba(255,255,255,0.94)';
      roundRect(ctx, bx, by, 24, 14, 4); ctx.fill();
      ctx.fillStyle = agent.pal.B;
      ctx.fillRect(bx + 5, by + 6, 3, 3);
      ctx.fillRect(bx + 11, by + 6, 3, 3);
      ctx.fillRect(bx + 17, by + 6, 3, 3);
    }
  }

  function drawCharacter(ctx, agent, ch, frame, ox, oy, px, T) {
    if (!agent.robot) {
      drawHumanCharacterV3(ctx, agent, ch, frame, ox, oy, T);
      return;
    }
    if (agent.id === 'aiky_main') {
      drawAikyCharacterV3(ctx, agent, ch, frame, ox, oy, T);
      return;
    }

    const tmpl = getSprite(agent, ch.state, ch.walkFrame, ch.typeFrame);
    const sprite = makeSprite(tmpl, agent.pal, px);
    let yOff = 0;
    if (ch.state === ST.IDLE) yOff = Math.sin(frame * 0.05 + agent.seatCol) * 1.5;

    // When typing/sitting: shift character down slightly to sit IN the chair
    const sittingOffset = ch.state === ST.TYPE ? px * 4 : 0;
    const sx = ox + ch.x - sprite.width / 2;
    const sy = oy + ch.y - sprite.height + sittingOffset;

    // Shadow (only when walking/standing)
    if (ch.state !== ST.TYPE) {
      ctx.fillStyle = 'rgba(0,0,0,0.2)';
      ctx.beginPath();
      ctx.ellipse(ox + ch.x, oy + ch.y + 2, 10, 4, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    const drawX = Math.round(sx), drawY = Math.round(sy + yOff);
    const outline = makeSilhouette(tmpl, 'rgba(11,13,18,0.92)', px);
    ctx.drawImage(outline, drawX - px, drawY);
    ctx.drawImage(outline, drawX + px, drawY);
    ctx.drawImage(outline, drawX, drawY - px);
    ctx.drawImage(outline, drawX, drawY + px);
    ctx.drawImage(sprite, drawX, drawY);
    drawCharacterDetails(ctx, agent, ch, drawX, drawY, px, frame);
    drawActivityProp(ctx, agent, ch, drawX, drawY, px, frame, ox, oy);
  }

  function drawCharacterDetails(ctx, agent, ch, sx, sy, px, frame) {
    const r = (col, row, w, h, color) => {
      drawPixelLine(ctx, sx + col * px, sy + row * px, w * px, h * px, color);
    };
    const activePulse = ch.isActive ? 0.55 + 0.35 * Math.sin(frame * 0.12) : 0.25;

    // Per-role pixel tailoring: hair silhouette, clothes, shoes, accessories.
    if (!agent.robot) {
      // Face polish: nose, cheeks and jaw shadow.
      r(7, 7, 1, 1, agent.pal.s);
      r(5, 8, 2, 1, 'rgba(255,146,120,0.45)');
      r(10, 8, 2, 1, 'rgba(255,146,120,0.38)');
      r(4, 9, 8, 1, agent.pal.s);

      if (agent.id === 'ceo_01' || agent.id === 'ui_01') {
        r(4, 6, 3, 1, '#101018'); r(9, 6, 3, 1, '#101018'); r(7, 6, 2, 1, '#101018');
        r(5, 7, 1, 1, 'rgba(255,255,255,0.55)'); r(10, 7, 1, 1, 'rgba(255,255,255,0.55)');
      }

      if (agent.id === 'ceo_01') {
        r(4, 1, 8, 1, '#D9A24A');
        r(3, 2, 3, 4, '#B8793A'); r(10, 2, 3, 4, '#B8793A');
        r(4, 12, 2, 6, '#F3F0E8'); r(10, 12, 2, 6, '#F3F0E8');
        r(6, 12, 4, 7, '#2F6FA7');
        r(7, 12, 2, 5, '#D84B3C');
        r(6, 28, 4, 2, '#201A18'); r(10, 28, 3, 2, '#201A18');
      }

      if (agent.id === 'cto_01' || agent.id === 'fe_01') {
        r(2, 9, 2, 6, '#151820'); r(12, 9, 2, 6, '#151820');
        r(3, 14, 3, 1, '#151820'); r(10, 14, 3, 1, '#151820');
        r(13, 8, 1, 7, agent.pal.B);
      }

      if (agent.id === 'cto_01') {
        r(4, 1, 8, 3, '#111118');
        r(3, 3, 2, 5, '#050508'); r(11, 3, 2, 5, '#050508');
        r(3, 12, 2, 7, '#F97316'); r(11, 12, 2, 7, '#F97316');
        r(5, 12, 6, 7, '#1D1D26');
        r(6, 15, 4, 1, '#EAB308');
      }

      if (agent.id === 'pm_01') {
        r(2, 2, 3, 12, '#D08A39'); r(11, 2, 3, 12, '#D08A39');
        for (let i = 0; i < 5; i++) r(4 + i * 2, 2 + i, 1, 9, i % 2 ? '#B86A2A' : '#E2A657');
        r(3, 10, 10, 1, '#F1C232');
        r(4, 12, 8, 7, '#242226');
        r(5, 18, 6, 2, '#111114');
      }

      if (agent.id === 'ui_01') {
        r(4, 1, 8, 2, '#111118');
        r(3, 2, 2, 8, '#1B1B22'); r(11, 2, 2, 8, '#1B1B22');
        r(4, 12, 8, 7, '#C92D45');
        r(7, 13, 2, 3, '#F6D7C8');
        r(5, 18, 6, 2, '#2B2B35');
      }

      if (agent.id === 'fe_01') {
        r(4, 0, 8, 4, '#F5F5F0');
        r(3, 3, 2, 5, '#D5D5D0'); r(11, 3, 2, 5, '#EAEAE5');
        r(5, 12, 6, 6, '#F2F2EA');
        r(7, 12, 2, 5, '#76A8C8');
        r(5, 18, 6, 2, '#7A838C');
      }

      if (agent.id === 'be_01') {
        r(5, 0, 3, 4, '#7A4317'); r(8, 0, 3, 5, '#5A2E0E');
        r(3, 3, 3, 4, '#7A4317'); r(11, 4, 2, 3, '#5A2E0E');
        r(5, 8, 6, 2, '#6A3518');
        r(6, 10, 4, 1, '#4C260E');
        r(4, 12, 8, 7, '#059669');
        r(7, 12, 2, 6, '#EAEFDF');
      }

      if (agent.id === 'qa_01') {
        r(4, 0, 7, 3, '#E43B18');
        r(2, 2, 4, 9, '#AA2200');
        r(11, 3, 3, 8, '#AA2200');
        r(4, 12, 8, 7, '#DC2626');
        r(4, 14, 8, 1, '#FFD166');
        r(6, 18, 4, 2, '#1F2937');
      }

      // Lanyard and small badge.
      r(7, 12, 1, 5, '#EDE9D5');
      r(8, 12, 1, 5, '#EDE9D5');
      r(7, 16, 2, 2, agent.pal.B);
      r(5, 29, 3, 2, '#111114');
      r(9, 29, 3, 2, '#111114');
      ctx.globalAlpha = activePulse;
      r(13, 12, 1, 1, agent.pal.B);
      ctx.globalAlpha = 1;
    } else {
      r(5, 1, 6, 2, '#AEB7FF');
      r(3, 3, 10, 5, '#5660D8');
      r(4, 9, 8, 2, '#3940A8');
      r(7, 0, 2, 1, '#B8C7FF');
      r(8, -2, 1, 2, '#B8C7FF');
      ctx.globalAlpha = 0.35 + 0.35 * Math.sin(frame * 0.12);
      r(5, 4, 2, 1, '#00F5FF'); r(10, 4, 2, 1, '#00F5FF');
      r(4, 12, 8, 1, '#00FF88');
      ctx.globalAlpha = 1;
      r(3, 17, 10, 1, '#3030AA');
    }

    if (agent.id === 'front_01') {
      r(4, 0, 8, 3, '#D99845');
      r(2, 2, 3, 12, '#B96A2C');
      r(12, 2, 3, 12, '#B96A2C');
      r(5, 3, 6, 1, '#F3C873');
      r(4, 12, 8, 1, '#F3D0DA');
      r(3, 13, 10, 5, '#EAB8C9');
      r(5, 18, 6, 2, '#2F2A32');
      r(5, 29, 3, 2, '#251814'); r(9, 29, 3, 2, '#251814');
    }

    if (ch.state === ST.TYPE) {
      r(3, 16, 3, 1, 'rgba(255,255,255,0.35)');
      r(10, 16, 3, 1, 'rgba(255,255,255,0.35)');
    }
  }

  function drawActivityProp(ctx, agent, ch, sx, sy, px, frame, ox, oy) {
    const r = (col, row, w, h, color) => {
      drawPixelLine(ctx, sx + col * px, sy + row * px, w * px, h * px, color);
    };
    const bob = Math.round(Math.sin(frame * 0.08 + ch.tileCol) * px);
    if (ch.state === ST.READ) {
      r(2, 14, 5, 5, '#F2E8C8');
      r(7, 14, 1, 5, '#B88735');
      r(8, 14, 5, 5, '#F2E8C8');
      r(3, 15, 3, 1, '#6E7FA8');
      r(9, 16, 3, 1, '#6E7FA8');
      ctx.fillStyle = 'rgba(255,245,190,0.18)';
      ctx.fillRect(sx + 2 * px, sy + 13 * px, 11 * px, 7 * px);
    } else if (ch.state === ST.DRINK) {
      r(11, 13, 3, 4, '#EDE9D5');
      r(12, 12, 1, 1, '#FFFFFF');
      r(14, 14, 1, 2, '#EDE9D5');
      ctx.globalAlpha = 0.45;
      r(12, 9 + (bob > 0 ? 1 : 0), 1, 2, '#DDEFF4');
      r(13, 8 + (bob > 0 ? 1 : 0), 1, 2, '#DDEFF4');
      ctx.globalAlpha = 1;
    } else if (ch.state === ST.CHAT) {
      const bx = ox + ch.x + 12;
      const by = oy + ch.y - SPR_H * px - 24 + bob;
      ctx.fillStyle = 'rgba(255,255,255,0.92)';
      roundRect(ctx, bx, by, 22, 14, 4); ctx.fill();
      ctx.fillStyle = agent.pal.B;
      ctx.fillRect(bx + 5, by + 6, 3, 3);
      ctx.fillRect(bx + 10, by + 6, 3, 3);
      ctx.fillRect(bx + 15, by + 6, 3, 3);
      ctx.fillStyle = 'rgba(255,255,255,0.92)';
      ctx.beginPath();
      ctx.moveTo(bx + 3, by + 11);
      ctx.lineTo(bx - 2, by + 16);
      ctx.lineTo(bx + 9, by + 12);
      ctx.closePath();
      ctx.fill();
    }
  }

  // ── Status bubble ──
  // Status label mapping
  const STATUS_CONFIG = {
    thinking: { icon: '🧠', label: '思考中', bg: '#6366f1' },
    working:  { icon: '⚙️', label: '工作中', bg: '#059669' },
    waiting:  { icon: '⏳', label: '等待中', bg: '#F59E0B' },
    speaking: { icon: '💬', label: '汇报中', bg: '#3B82F6' },
  };

  function isDuplicateActionText(action, status, cfg) {
    if (!action || !action.trim()) return true;
    const text = action.trim().toLowerCase();
    return text === status || text === cfg.label.toLowerCase() || text === '工作中';
  }

  function drawBubble(ctx, agent, ch, frame, ox, oy, px) {
    const status = ch.agentStatus;
    if (status === 'idle') return;
    const tag = getNameTagGeometry(ctx, agent, ch, ox, oy, px);
    const bx = tag.cx;
    const color = agent.pal.B;
    const cfg = STATUS_CONFIG[status];
    if (!cfg) return;

    // ── Status badge (pill shape) ──
    const statusText = cfg.icon + ' ' + cfg.label;
    ctx.font = 'bold 11px Inter, Arial, sans-serif';
    ctx.textAlign = 'center';
    const sw = ctx.measureText(statusText).width + 14;
    const sh = 20;
    const hasAction = !isDuplicateActionText(ch.action, status, cfg);
    const by = tag.y - 8;
    const sx = bx - sw / 2, sy = by - sh;

    // Glow pulse
    const pulse = 0.85 + 0.15 * Math.sin(frame * 0.08);
    ctx.globalAlpha = pulse;

    // Background pill
    ctx.fillStyle = cfg.bg;
    roundRect(ctx, sx, sy, sw, sh, 10); ctx.fill();

    // Text
    ctx.fillStyle = '#ffffff';
    ctx.fillText(statusText, bx, sy + 14);
    ctx.globalAlpha = 1;

    // Small triangle pointer
    ctx.fillStyle = cfg.bg;
    ctx.globalAlpha = pulse;
    ctx.beginPath();
    ctx.moveTo(bx - 4, sy + sh);
    ctx.lineTo(bx + 4, sy + sh);
    ctx.lineTo(bx, sy + sh + 5);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;

    // ── Action text (below status badge, above character) ──
    if (hasAction) {
      const text = ch.action.length > 20 ? ch.action.substring(0, 20) + '\u2026' : ch.action;
      ctx.font = '10px Inter, Arial, sans-serif';
      const tw = ctx.measureText(text).width + 16;
      const th = 18;
      const ty = sy - th - 4;

      // Dark background pill
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      roundRect(ctx, bx - tw/2, ty, tw, th, 6); ctx.fill();
      // Left accent
      ctx.fillStyle = color;
      ctx.fillRect(bx - tw/2 + 3, ty + 3, 2, th - 6);
      // Text
      ctx.fillStyle = '#ddd'; ctx.textAlign = 'center';
      ctx.fillText(text, bx + 2, ty + 13);

      // Small triangle
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      ctx.beginPath();
      ctx.moveTo(bx - 3, ty + th);
      ctx.lineTo(bx + 3, ty + th);
      ctx.lineTo(bx, ty + th + 4);
      ctx.closePath();
      ctx.fill();
    }
  }

  function getNameTagGeometry(ctx, agent, ch, ox, oy, px) {
    const cx = ox + ch.x, cy = oy + ch.y;
    const sittingOffset = ch.state === ST.TYPE ? px * 4 : 0;
    ctx.font = 'bold 13px Inter, Arial, sans-serif';
    const nw = ctx.measureText(agent.name).width;
    ctx.font = '11px Inter, Arial, sans-serif';
    const tw = ctx.measureText(agent.title).width;
    const w = Math.max(nw, tw) + 18;
    const h = 30;
    const aboveHead = cy - characterTagHeight(agent, ch) - 4 + sittingOffset;
    return { cx, cy, x: cx - w / 2, y: aboveHead - h, w, h };
  }

  function drawNameTag(ctx, agent, ch, ox, oy, px) {
    const name = agent.name;
    const title = agent.title;
    const tag = getNameTagGeometry(ctx, agent, ch, ox, oy, px);
    const cx = tag.cx;
    // Dark background with solid fill for readability
    ctx.fillStyle = 'rgba(15,15,30,0.88)';
    roundRect(ctx, tag.x, tag.y, tag.w, tag.h, 6);
    ctx.fill();
    // Colored top accent line
    ctx.fillStyle = agent.pal.B;
    ctx.fillRect(tag.x + 4, tag.y + 1, tag.w - 8, 2);
    // Name — bold white, large
    ctx.font = 'bold 13px Inter, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(name, cx, tag.y + 16);
    // Title — bright colored
    ctx.font = '11px Inter, Arial, sans-serif';
    ctx.fillStyle = agent.pal.B;
    ctx.globalAlpha = 1;
    ctx.fillText(title, cx, tag.y + 27);
    ctx.globalAlpha = 1;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y);
    ctx.quadraticCurveTo(x+w,y,x+w,y+r); ctx.lineTo(x+w,y+h-r);
    ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h); ctx.lineTo(x+r,y+h);
    ctx.quadraticCurveTo(x,y+h,x,y+h-r); ctx.lineTo(x,y+r);
    ctx.quadraticCurveTo(x,y,x+r,y); ctx.closePath();
  }

  // ══════════════════════════════════════════════════════════════
  // 6. PIXEL OFFICE CLASS
  // ══════════════════════════════════════════════════════════════

  class PixelOffice {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.frame = 0;
      this.lastTime = 0;
      this.particles = [];
      this.running = false;
      this._envCache = null;
      this._envSize = { w: 0, h: 0 };

      // Initialize characters with state machine
      this.chars = {};
      // Use initial tile size for positioning
      const initT = calcTile(canvas.width || 800, canvas.height || 600);
      for (const ag of AGENTS) {
        const cx = (ag.seatCol + 0.5) * initT;
        const cy = (ag.seatRow + 0.5) * initT;
        this.chars[ag.id] = {
          x: cx, y: cy,
          tileCol: ag.seatCol, tileRow: ag.seatRow,
          state: ST.TYPE, // start typing
          agentStatus: 'idle',
          action: '',
          isActive: false,
          path: [],
          moveProgress: 0,
          walkFrame: 0, walkTimer: 0,
          typeFrame: 0, typeTimer: 0,
          wanderTimer: 10 + Math.random() * 16,
          wanderCount: 0,
          nextState: null,
          activityTimer: 0,
          activityDuration: 0,
        };
      }

      if (!canvas.width || canvas.width < 10) canvas.width = 800;
      if (!canvas.height || canvas.height < 10) canvas.height = 600;
      console.log('[PixelOffice v3] Init:', canvas.width, 'x', canvas.height);
      this._startLoop();
    }

    setAgentState(id, status, action) {
      const ch = this.chars[id];
      if (!ch) return;
      const wasIdle = !ch.isActive;
      ch.agentStatus = status || 'idle';
      ch.action = action || '';
      ch.isActive = status && status !== 'idle';

      if (wasIdle && ch.isActive) {
        // Agent became active → pathfind to seat
        const ag = AGENTS.find(a => a.id === id);
        if (ag) {
          this._pathToSeat(ch, ag);
          this._spawnBurst(ch.x, ch.y, ag.pal.B, 10);
        }
      } else if (!wasIdle && !ch.isActive) {
        // Agent became idle → start wandering after delay
        ch.wanderTimer = 8 + Math.random() * 12;
        ch.wanderCount = 0;
        if (ch.state === ST.TYPE) {
          ch.state = ST.IDLE;
        }
      }
    }

    _pathToSeat(ch, ag) {
      const path = findPath(ch.tileCol, ch.tileRow, ag.seatCol, ag.seatRow);
      if (path.length > 0) {
        ch.path = path;
        ch.moveProgress = 0;
        ch.state = ST.WALK;
        ch.walkFrame = 0;
        ch.nextState = ST.TYPE;
        ch.activityDuration = 0;
      } else {
        // Already at seat
        ch.state = ST.TYPE;
        ch.typeFrame = 0;
        ch.nextState = null;
      }
    }

    _pathToActivity(ch, spot) {
      const path = findPath(ch.tileCol, ch.tileRow, spot.col, spot.row);
      ch.nextState = spot.state;
      ch.activityDuration = spot.duration || 3.5;
      if (path.length > 0) {
        ch.path = path;
        ch.moveProgress = 0;
        ch.state = ST.WALK;
        ch.walkFrame = 0;
      } else {
        ch.state = spot.state;
        ch.activityTimer = ch.activityDuration;
      }
    }

    _isTileOccupied(col, row, selfId) {
      for (const ag of AGENTS) {
        if (ag.id === selfId) continue;
        const other = this.chars[ag.id];
        if (!other) continue;
        if (other.tileCol === col && other.tileRow === row) return true;
        const next = other.path && other.path[0];
        if (next && next.col === col && next.row === row) return true;
      }
      return false;
    }

    _openSpots(spots, selfId) {
      return spots.filter(spot => !this._isTileOccupied(spot.col, spot.row, selfId));
    }

    _chooseIdleActivity(ch, ag) {
      if (ag.npc) {
        const spots = this._openSpots(RECEPTION_SPOTS, ag.id);
        const spot = spots.length ? spots[Math.floor(Math.random() * spots.length)] : null;
        if (!spot) { this._pathToSeat(ch, ag); return; }
        this._pathToActivity(ch, spot);
        return;
      }
      const roll = Math.random();
      if (roll < 0.22) {
        const spots = this._openSpots(DAILY_SPOTS, ag.id);
        const spot = spots.length ? spots[Math.floor(Math.random() * spots.length)] : null;
        if (spot) {
          this._pathToActivity(ch, spot);
          return;
        }
      }
      if (roll < 0.78) {
        this._pathToSeat(ch, ag);
        return;
      }

      const targets = [];
      for (let r = 0; r < MAP_ROWS; r++)
        for (let c = 0; c < MAP_COLS; c++)
          if (isWalkable(c, r) && !this._isTileOccupied(c, r, ag.id)) targets.push({col:c, row:r});
      if (targets.length > 0) {
        const t = targets[Math.floor(Math.random()*targets.length)];
        const path = findPath(ch.tileCol, ch.tileRow, t.col, t.row);
        if (path.length > 0 && path.length < 8) {
          ch.path = path;
          ch.moveProgress = 0;
          ch.state = ST.WALK;
          ch.walkFrame = 0;
          ch.nextState = ST.IDLE;
          ch.activityDuration = 0;
          ch.wanderCount++;
        }
      }
    }

    resize(w, h) {
      const nw = Math.max(100, Math.floor(w));
      const nh = Math.max(100, Math.floor(h));
      if (this.canvas.width !== nw || this.canvas.height !== nh) {
        this.canvas.width = nw;
        this.canvas.height = nh;
        this._envCache = null;
      }
    }

    _spawnBurst(x, y, color, n) {
      for (let i = 0; i < n; i++) {
        const angle = (Math.PI * 2 * i) / n + Math.random() * 0.4;
        const spd = 1.5 + Math.random() * 3;
        this.particles.push({
          x, y, vx: Math.cos(angle)*spd, vy: Math.sin(angle)*spd - 1,
          color, life: 40 + Math.random() * 20, maxLife: 60, size: 2+Math.random()*2
        });
      }
    }

    _updateVisualSpacing(T) {
      const chars = Object.values(this.chars);
      for (const ch of chars) {
        ch.visualOffsetX = 0;
        ch.visualOffsetY = 0;
      }
      const minDist = T * 0.42;
      for (let i = 0; i < AGENTS.length; i++) {
        const a = this.chars[AGENTS[i].id];
        if (!a) continue;
        for (let j = i + 1; j < AGENTS.length; j++) {
          const b = this.chars[AGENTS[j].id];
          if (!b) continue;
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.hypot(dx, dy);
          if (dist > 0 && dist < minDist) {
            const push = (minDist - dist) * 0.28;
            const nx = dx / dist, ny = dy / dist;
            a.visualOffsetX += nx * push;
            a.visualOffsetY += ny * push * 0.35;
            b.visualOffsetX -= nx * push;
            b.visualOffsetY -= ny * push * 0.35;
          } else if (dist === 0 && a !== b) {
            const dir = i % 2 === 0 ? 1 : -1;
            a.visualOffsetX += dir * 4;
            b.visualOffsetX -= dir * 4;
          }
        }
      }
    }

    // ── Update character states ──
    _updateChars(dt, T) {
      const walkSpeed = calcWalkSpeed(T);
      for (const ag of AGENTS) {
        const ch = this.chars[ag.id];
        if (!ch) continue;

        switch (ch.state) {
          case ST.TYPE:
            ch.typeTimer += dt;
            if (ch.typeTimer >= TYPE_FRAME_DUR) {
              ch.typeTimer -= TYPE_FRAME_DUR;
              ch.typeFrame = (ch.typeFrame + 1) % 2;
            }
            // Keep position synced with dynamic tile size
            ch.x = (ch.tileCol + 0.5) * T;
            ch.y = (ch.tileRow + 0.5) * T;
            if (!ch.isActive) {
              ch.wanderTimer -= dt;
              if (ch.wanderTimer <= 0) {
                if (ag.npc || Math.random() < 0.24) {
                  ch.state = ST.IDLE;
                  ch.wanderTimer = 0.4 + Math.random() * 1.2;
                } else {
                  ch.wanderTimer = 10 + Math.random() * 18;
                }
              }
            }
            break;

          case ST.READ:
          case ST.DRINK:
          case ST.CHAT:
          case ST.MEET:
            if (ch.isActive) {
              this._pathToSeat(ch, ag);
              break;
            }
            ch.typeTimer += dt;
            if (ch.typeTimer >= TYPE_FRAME_DUR) {
              ch.typeTimer -= TYPE_FRAME_DUR;
              ch.typeFrame = (ch.typeFrame + 1) % 2;
            }
            ch.x = (ch.tileCol + 0.5) * T;
            ch.y = (ch.tileRow + 0.5) * T;
            ch.activityTimer -= dt;
            if (ch.activityTimer <= 0) {
              this._pathToSeat(ch, ag);
              ch.nextState = null;
              ch.wanderTimer = 8 + Math.random() * 14;
            }
            break;

          case ST.IDLE:
            // Keep position synced
            if (ch.path.length === 0) {
              ch.x = (ch.tileCol + 0.5) * T;
              ch.y = (ch.tileRow + 0.5) * T;
            }
            if (ch.isActive) {
              this._pathToSeat(ch, ag);
              break;
            }
            ch.wanderTimer -= dt;
            if (ch.wanderTimer <= 0) {
              this._chooseIdleActivity(ch, ag);
              ch.wanderTimer = 8 + Math.random() * 14;
              if (ch.wanderCount >= 2 + Math.floor(Math.random()*3)) {
                this._pathToSeat(ch, ag);
                ch.wanderCount = 0;
              }
            }
            break;

          case ST.WALK:
            ch.walkTimer += dt;
            if (ch.walkTimer >= WALK_FRAME_DUR) {
              ch.walkTimer -= WALK_FRAME_DUR;
              ch.walkFrame = (ch.walkFrame + 1) % 4;
            }
            if (ch.path.length === 0) {
              if (ch.isActive && ch.tileCol === ag.seatCol && ch.tileRow === ag.seatRow) {
                ch.state = ST.TYPE;
                ch.typeFrame = 0;
              } else if (ch.nextState && ch.nextState !== ST.IDLE) {
                ch.state = ch.nextState;
                ch.activityTimer = ch.activityDuration || 3.5;
                if (ch.state === ST.TYPE) ch.typeFrame = 0;
                ch.nextState = null;
              } else {
                if (!ag.npc && Math.random() < 0.65) {
                  this._pathToSeat(ch, ag);
                } else {
                  ch.state = ST.IDLE;
                  ch.wanderTimer = 4 + Math.random() * 7;
                  ch.nextState = null;
                }
              }
              break;
            }
            const next = ch.path[0];
            if (ch.moveProgress === 0 && this._isTileOccupied(next.col, next.row, ag.id)) {
              ch.walkTimer = 0;
              break;
            }
            const fromX = (ch.tileCol + 0.5) * T;
            const fromY = (ch.tileRow + 0.5) * T;
            const toX = (next.col + 0.5) * T;
            const toY = (next.row + 0.5) * T;
            ch.moveProgress += (walkSpeed / T) * dt;
            const t = Math.min(ch.moveProgress, 1);
            ch.x = fromX + (toX - fromX) * t;
            ch.y = fromY + (toY - fromY) * t;
            if (ch.moveProgress >= 1) {
              ch.tileCol = next.col;
              ch.tileRow = next.row;
              ch.x = toX; ch.y = toY;
              ch.path.shift();
              ch.moveProgress = 0;
            }
            if (ch.isActive) {
              const last = ch.path[ch.path.length - 1];
              if (!last || last.col !== ag.seatCol || last.row !== ag.seatRow) {
                const np = findPath(ch.tileCol, ch.tileRow, ag.seatCol, ag.seatRow);
                if (np.length > 0) { ch.path = np; ch.moveProgress = 0; }
              }
          }
            break;
        }
      }
      this._updateVisualSpacing(T);
    }

    // ── Build environment cache ──
    _buildEnvCache() {
      const W = this.canvas.width, H = this.canvas.height;
      const T = calcTile(W, H);
      if (this._envCache && this._envSize.w === W && this._envSize.h === H) return T;
      const c = document.createElement('canvas');
      c.width = W; c.height = H;
      const ctx = c.getContext('2d');

      ctx.fillStyle = '#12121e'; ctx.fillRect(0, 0, W, H);

      const mapW = MAP_COLS * T, mapH = MAP_ROWS * T;
      const ox = Math.floor((W - mapW) / 2);
      const oy = Math.floor((H - mapH) / 2);
      this._ox = ox; this._oy = oy;

      drawTileMap(ctx, ox, oy, T);
      drawFineOfficeTexture(ctx, ox, oy, T);
      drawWindows(ctx, ox, oy, T);

      // Wall furniture and room details, inspired by classic top-down pixel offices.
      drawBookshelf(ctx, ox + sp(T, 6), oy + T + sp(T, 6), T, 2);
      drawBookshelf(ctx, ox + 3 * T + sp(T, 6), oy + T + sp(T, 6), T, 2);
      drawBookshelf(ctx, ox + 9 * T + sp(T, 6), oy + 7 * T + sp(T, 7), T, 2);
      drawBookshelf(ctx, ox + 15 * T - sp(T, 4), oy + 7 * T + sp(T, 7), T, 2);

      drawVendingMachine(ctx, ox + 9 * T + sp(T, 5), oy + T + sp(T, 2), T);
      drawWaterCooler(ctx, ox + 10 * T + sp(T, 6), oy + T + sp(T, 1), T);
      drawFileCabinet(ctx, ox + 13 * T + sp(T, 5), oy + T + sp(T, 2), T);
      drawVisitorBench(ctx, ox + 14 * T + sp(T, 4), oy + 3 * T + sp(T, 8), T);
      drawFramedPicture(ctx, ox + 12 * T + sp(T, 3), oy + 6 * T + sp(T, 4), T);
      drawMeetingNook(ctx, ox + 12 * T + sp(T, 2), oy + 8 * T + sp(T, 4), T);
      drawConferenceTable(ctx, ox + 11 * T + sp(T, 4), oy + 11 * T + sp(T, 6), T);
      drawSideTV(ctx, ox + 15 * T + sp(T, 7), oy + 10 * T + sp(T, 4), T);
      drawFloorLamp(ctx, ox + 17 * T - sp(T, 18), oy + 11 * T + sp(T, 18), T);

      drawClock(ctx, ox + 7.6 * T, oy + T * 0.42);
      drawWhiteboard(ctx, ox + 16 * T, oy, T);

      drawPlant(ctx, ox - 4, oy + MAP_ROWS * T - T);
      drawPlant(ctx, ox + mapW - T + 4, oy + MAP_ROWS * T - T);
      drawPlant(ctx, ox + 10 * T, oy + MAP_ROWS * T - T);
      drawPlant(ctx, ox + 8 * T + sp(T, 5), oy + 6 * T + sp(T, 3));
      drawPlant(ctx, ox + 16 * T + sp(T, 8), oy + 5 * T + sp(T, 5));

      // Desks NOT drawn here — they go into Z-sorted render loop
      // so they render ON TOP of characters sitting behind them

      ctx.font = 'bold 9px monospace';
      ctx.fillStyle = 'rgba(99,102,241,0.4)';
      ctx.textAlign = 'left';
      ctx.fillText('AI OFFICE', ox + 4, oy - 4);

      this._envCache = c;
      this._envSize = { w: W, h: H };
      return T;
    }

    // ── Main render ──
    render(timestamp) {
      const dt = this.lastTime ? Math.min((timestamp - this.lastTime) / 1000, 0.1) : 0.016;
      this.lastTime = timestamp;

      const { ctx, canvas } = this;
      const W = canvas.width, H = canvas.height;
      if (W < 10 || H < 10) return;

      ctx.imageSmoothingEnabled = false;
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;

      try {
        // Update character states
        const T = this._buildEnvCache();
        const px = calcPX(T);
        this._updateChars(dt, T);

        // Draw cached environment
        ctx.drawImage(this._envCache, 0, 0);
        const ox = this._ox, oy = this._oy;

        // Collect Z-sorted drawables: chairs, desks, characters
        const drawables = [];

        // Reception counter sits in front of Mia and masks her lower body like a real front desk.
        drawables.push({
          zY: 4 * T + T * 0.85,
          draw: () => drawReceptionDesk(ctx, ox + 11 * T + sp(T, 4), oy + 4 * T + sp(T, 2), T)
        });

        // Chairs (drawn at their tile position)
        for (let r = 0; r < MAP_ROWS; r++)
          for (let c = 0; c < MAP_COLS; c++)
            if (TILE_MAP[r][c] === 'C') {
              const cr = r, cc = c;
              drawables.push({ zY: r * T + T * 0.5, draw: () => drawChair(ctx, ox + cc * T, oy + cr * T, T) });
            }

        // ALL Desks (Z-sorted so they render OVER characters sitting behind)
        // Check if any agent is active at this desk for glow effect
        for (let r = 0; r < MAP_ROWS; r++)
          for (let c = 0; c < MAP_COLS; c++)
            if (TILE_MAP[r][c] === 'D') {
              const dr = r, dc = c;
              // Check if an agent has their desk here (desk is 1 row below seat)
              let isActive = false;
              let deskColor = '#555';
              for (const ag of AGENTS) {
                if (ag.seatRow + 1 === dr && ag.seatCol === dc) {
                  const ch2 = this.chars[ag.id];
                  if (ch2 && ch2.isActive) { isActive = true; deskColor = ag.pal.B; }
                  break;
                }
              }
              drawables.push({
                zY: r * T + T * 0.45, // desk top reaches toward the chair row
                draw: () => drawDesk(ctx, ox + dc * T, oy + dr * T, isActive, deskColor, this.frame, T)
              });
            }

        // Characters
        for (const ag of AGENTS) {
          const ch = this.chars[ag.id];
          if (!ch) continue;
          const drawCh = {
            ...ch,
            x: ch.x + (ch.visualOffsetX || 0),
            y: ch.y + (ch.visualOffsetY || 0)
          };
          const charZY = drawCh.state === ST.TYPE ? drawCh.y + T * 0.16 : drawCh.y + T * 0.3;
          drawables.push({
            zY: charZY,
            draw: () => {
              drawCharacter(ctx, ag, drawCh, this.frame, ox, oy, px, T);
              drawBubble(ctx, ag, drawCh, this.frame, ox, oy, px);
              drawNameTag(ctx, ag, drawCh, ox, oy, px);
            }
          });
        }

        drawables.sort((a, b) => a.zY - b.zY);
        for (const d of drawables) d.draw();

        // Particles
        this._drawParticles(ctx, ox, oy);

        // Scanlines
        ctx.fillStyle = 'rgba(0,0,0,0.03)';
        for (let y = 0; y < H; y += 3) ctx.fillRect(0, y, W, 1);

      } catch (e) {
        if (this.frame < 5) console.error('[PixelOffice v3] Render error:', e);
      }
      this.frame++;
    }

    _drawParticles(ctx, ox, oy) {
      this.particles = this.particles.filter(p => p.life > 0);
      for (const p of this.particles) {
        const t = 1 - p.life / p.maxLife;
        ctx.fillStyle = p.color;
        ctx.globalAlpha = Math.pow(1 - t, 1.5) * 0.85;
        ctx.fillRect(
          Math.round(ox + p.x + p.vx * t * p.maxLife),
          Math.round(oy + p.y + p.vy * t * p.maxLife + 30 * t * t),
          Math.round(p.size), Math.round(p.size)
        );
        p.life--;
      }
      ctx.globalAlpha = 1;
    }

    _startLoop() {
      if (this.running) return;
      this.running = true;
      const tick = (ts) => { this.render(ts); requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    }
  }

  window.PixelOffice = PixelOffice;
})();
