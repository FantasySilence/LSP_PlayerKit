/**
 * 前端入口（main.ts）
 *
 * 这个文件是整个 Web 前端的启动点：创建 Vue 应用实例，把根组件 App.vue
 * 挂载到 index.html 里的 #app 节点上，并先加载全局样式。
 *
 * 交互关系：
 * - App.vue 是唯一根组件，负责工具轨、命令栏与工作区的整体布局；
 * - base.css 会 @import 设计令牌（tokens.css）并定义全站通用样式；
 * - 其余模块（platform/*、shell/*、ui/*）都由 App.vue 按需引入。
 *
 * 这里不包含任何业务逻辑，只负责“把界面跑起来”。
 */

import { createApp } from 'vue'

// App.vue：应用外壳，内部再按当前工具 id 懒加载各工具视图
import App from './App.vue'
// base.css：全站基础样式（含设计令牌），必须在挂载前引入
import './styles/base.css'

// 创建应用并以 App.vue 为根组件，挂载到 index.html 中的 #app 容器
createApp(App).mount('#app')
