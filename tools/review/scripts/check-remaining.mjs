#!/usr/bin/env node
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));

// 48 个之前无 CDN URL 的 slug 列表
const remainingSlugs = [
  // pending (39)
  'yida/custom-page/eab1wa',
  'yida/form/ad122fe2ufqbog42',
  'yida/form/ah8b9z',
  'yida/form/cwczglfr7liddmmw',
  'yida/form/ddsy93l7tdtf3s9s',
  'yida/form/dzzlham7l7xfr6wo',
  'yida/form/escqg551suxgr6gq',
  'yida/form/evp4gkq8kcv4hgga',
  'yida/form/ewow48u8pg6wde0y',
  'yida/form/fs8ym2',
  'yida/form/hf8nma',
  'yida/form/hkv6w6z366q9mg7i',
  'yida/form/iak2o5xcbksb13wz',
  'yida/form/ig680t7ur2cl0y4d',
  'yida/form/igrvxuztr0syw9sn',
  'yida/form/klvwx6gxfw6g6fgs',
  'yida/form/kruy97m10v8mt3mt',
  'yida/form/lks3ggo5cktvq213',
  'yida/form/mu292cs9i21m82yh',
  'yida/form/nvnp2kkbb94y8u9e',
  'yida/form/obwipf12ew36n32a',
  'yida/form/oyuexdmpaxiys2tm',
  'yida/form/pkiwut48qyfax6h5',
  'yida/form/pvw37ge84kxg9x28',
  'yida/form/qfwh5ivncnfg57wt',
  'yida/form/qtvvfx4e7ze0vvbb',
  'yida/form/rcyqy4mriwgq5nc2',
  'yida/form/rzixdcx24zsd1ldx',
  'yida/form/sprth45e4nh19yhw',
  'yida/form/sxc8gv9dkhmt8zro',
  'yida/form/uobzicixvh02io31',
  'yida/form/vgvc4f7myfwpbqa5',
  'yida/form/vs0ddo8m5ggofmtb',
  'yida/form/vwncwe',
  'yida/form/wn65drd666xdl3b1',
  'yida/form/xdtv56ngunnhppyw',
  'yida/form/zl5s2mdi2ue214n4',
  'yida/form/zrgy7twy6d9ry6ey',
  'yida/process/ywnn9itpk2e52332',
  // prepared (3)
  'yida/app-admin/lwburt',
  'yida/custom-page/hndctc',
  'yida/form/rea5br',
  // skipped (5)
  'yida/portal/wohqsumlwfir3d4u',
  'yida/report/aii2tp',
  'yida/report/ox8nu4',
  'yida/report/pf0tv9',
  'yida/report/sfbgoc',
  // mixed (1)
  'yida/form/uyznm2o4advaans7',
];

// 重新检查每个 slug 的当前 batch items 状态
let canProcessNow = [];   // 有 completed items 可以回写
let stillPending = [];     // 仍然全部 pending
let stillSkipped = [];     // 仍然全部 skipped
let stillPrepared = [];    // 仍然全部 prepared
let stillMixed = [];       // 混合状态
let notInBatch = [];       // 不在 batch 中

for (const slug of remainingSlugs) {
  const items = (batch.items || []).filter(i => i.slug === slug);
  if (items.length === 0) {
    notInBatch.push(slug);
    continue;
  }

  // 检查是否有任何已完成的 items（有 cdnUrl 或 target.currentUrl）
  const completedItems = items.filter(i => {
    if (i.status !== 'completed') return false;
    const cdnUrl = i.cdnUrl || i.target?.currentUrl;
    return !!cdnUrl;
  });

  // 检查 EN 文件中是否已有这些 CDN URL
  const enFile = join(repoRoot, slug + '.mdx');
  if (completedItems.length > 0) {
    let alreadyInFile = 0;
    let needWrite = 0;
    if (existsSync(enFile)) {
      const content = readFileSync(enFile, 'utf8');
      for (const item of completedItems) {
        const cdnUrl = item.cdnUrl || item.target?.currentUrl;
        if (content.includes(cdnUrl)) alreadyInFile++;
        else needWrite++;
      }
    } else {
      needWrite = completedItems.length;
    }

    if (needWrite > 0) {
      canProcessNow.push({
        slug,
        completedCount: completedItems.length,
        needWrite,
        alreadyInFile,
        totalItems: items.length,
        allStatuses: items.reduce((acc, i) => { acc[i.status] = (acc[i.status] || 0) + 1; return acc; }, {}),
      });
    } else if (alreadyInFile === completedItems.length) {
      // 所有 completed items 都已在文件中，但可能还有 pending/skipped
      const otherStatuses = items.filter(i => i.status !== 'completed');
      if (otherStatuses.length > 0) {
        stillMixed.push({
          slug,
          completedInFile: alreadyInFile,
          otherStatuses: otherStatuses.reduce((acc, i) => { acc[i.status] = (acc[i.status] || 0) + 1; return acc; }, {}),
        });
      }
    }
  } else {
    // 没有 completed items
    const statuses = items.reduce((acc, i) => { acc[i.status] = (acc[i.status] || 0) + 1; return acc; }, {});
    const statusKeys = Object.keys(statuses);
    if (statusKeys.length === 1) {
      if (statuses.pending) stillPending.push({ slug, count: items.length });
      else if (statuses.skipped) stillSkipped.push({ slug, count: items.length });
      else if (statuses.prepared) stillPrepared.push({ slug, count: items.length });
    } else {
      stillMixed.push({ slug, statuses, totalItems: items.length });
    }
  }
}

console.log('=== 剩余 48 个文件当前状态检查 ===\n');

console.log(`可以立即回写（有 completed items 未在 EN 文件中）: ${canProcessNow.length}`);
if (canProcessNow.length > 0) {
  for (const f of canProcessNow.sort((a, b) => b.needWrite - a.needWrite)) {
    console.log(`  ${f.slug}: 需回写 ${f.needWrite}/${f.completedCount} completed (总 ${f.totalItems} items, 状态: ${JSON.stringify(f.allStatuses)})`);
  }
}

console.log(`\n仍然全部 pending: ${stillPending.length}`);
for (const f of stillPending) {
  console.log(`  ${f.slug}: ${f.count} pending`);
}

console.log(`\n仍然全部 skipped: ${stillSkipped.length}`);
for (const f of stillSkipped) {
  console.log(`  ${f.slug}: ${f.count} skipped`);
}

console.log(`\n仍然全部 prepared: ${stillPrepared.length}`);
for (const f of stillPrepared) {
  console.log(`  ${f.slug}: ${f.count} prepared`);
}

console.log(`\n混合状态: ${stillMixed.length}`);
for (const f of stillMixed) {
  const s = JSON.stringify(f.statuses || {});
  console.log('  ' + f.slug + ': ' + s + ' / completedInFile=' + (f.completedInFile || 0));
}

console.log(`\n不在 batch 中: ${notInBatch.length}`);
for (const s of notInBatch) {
  console.log(`  ${s}`);
}
