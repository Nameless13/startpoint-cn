import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"

// dev: 5173, /api 代理到 CN 服务（默认 localhost:8001）
// 若 CN_LISTEN_HOST 绑定了 LAN IP，在 admin/.env 里设 VITE_API_TARGET 覆盖
// build: 产物输出到 ../web/dist，由 cn-server 挂载在 /admin
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), "")
    const apiTarget = env.VITE_API_TARGET || "http://localhost:8001"
    return {
        plugins: [react()],
        base: "/admin/",
        server: {
            port: 5173,
            proxy: {
                "/api": {
                    target: apiTarget,
                    // 保留浏览器 Host，使 Cookie 写请求的 Origin/Host 同源校验成立。
                    changeOrigin: false
                }
            }
        },
        build: {
            outDir: "../web/dist",
            emptyOutDir: true,
            chunkSizeWarningLimit: 900,
            rolldownOptions: {
                output: {
                    codeSplitting: {
                        groups: [
                            {
                                // 按包边界拆而不用 maxSize 自动切:自动切会把互相依赖的模块
                                // 切进不同分片(求值期跨片读 KeyCode 得 undefined => /admin 白屏)。
                                // icons/rc-* 只被 antd 单向依赖,无环,求值顺序安全。
                                name: "vendor-icons",
                                test: /[\\/]node_modules[\\/]@ant-design[\\/]icons/,
                                priority: 50
                            },
                            {
                                name: "vendor-rc",
                                test: /[\\/]node_modules[\\/](?:@rc-component[\\/]|rc-[^\\/]+[\\/])/,
                                priority: 45
                            },
                            {
                                name: "vendor-antd",
                                test: /[\\/]node_modules[\\/](?:antd[\\/]|@ant-design[\\/])/,
                                priority: 40
                            },
                            {
                                name: "vendor-query",
                                test: /[\\/]node_modules[\\/]@tanstack[\\/]/,
                                priority: 30
                            },
                            {
                                name: "vendor-react",
                                test: /[\\/]node_modules[\\/](?:react(?:-dom|-router|-router-dom)?|scheduler|@remix-run)[\\/]/,
                                priority: 20
                            },
                            {
                                name: "vendor-misc",
                                test: /[\\/]node_modules[\\/]/,
                                priority: 10,
                                maxSize: 600 * 1024
                            }
                        ]
                    }
                }
            }
        }
    }
})
