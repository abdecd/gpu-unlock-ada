# Ubuntu 22.04 / RTX 3090 独立解锁镜像

基于上游 main `d28c485`，使用 initramfs-tools 构建独立解锁镜像。
目标环境：Ubuntu 22.04、initramfs-tools、GA102 `10de:2204`，支持通过上游参数选择单卡、多卡或 all。
## 已验证环境

已在 Ubuntu 22.04、内核 `5.15.0-203-generic`、NVIDIA `550.90.07`、
四张 MSI RTX 3090（GA102 `10de:2204`）上完成：私有模块编译、独立镜像构建和审计、
手动选择专用 GRUB 项启动、逐卡 `gpu_unlock: unlocked` 日志核对，以及四卡数值/性能测试。
普通内核和 initrd 保持不变，GRUB 默认仍为普通 Ubuntu。
这代表该环境的一次启动及短时测试通过，不保证其他机器、内核或长期负载稳定性。

## 启动注意事项

固件/内核挂死仍可能需要现场断电，只有 SSH 不能保证恢复。
本目录构建脚本不执行任何 GPU 加载、解绑、重置、关机、重启或 GRUB 改写；
只有选择专用镜像启动时，镜像内 gate 才会加载模块。
首次启动测试应准备可用的控制台或现场恢复方式。

## 镜像与更新方式

- 使用 mkinitramfs 生成 `/boot/initrd.img-<kernel>-server3090`。
- 普通 `/boot/initrd.img-<kernel>` 和内核文件保持不变，构建前后校验哈希。
- **不注册 DKMS、不安装全局 gpu_unlock.ko、不安装更新钩子**：
  模块在临时目录针对指定 headers 编译，只装入专用镜像。
  避免 initramfs-tools 的依赖扫描把全局模块和固件带进普通镜像。
- 固件按清单固定 SHA-256 校验；更新内核只需重新编译模块/打包，不必重新生成固件。
- 新内核需要手动运行构建脚本，使用与内核版本匹配的专用镜像。
- 不使用上游 `make install` 或安装 .deb；后者会更新普通 initrd，不符合这里的隔离策略。

## 构建

需要 gcc、make、python3、zstd、kmod、initramfs-tools、目标内核 headers。
模块还依赖内核 SHA-256 API；当前 5.15.0-203 已通过实际编译，其他版本仍需逐一确认，
失败应停止，不绕过或自动修改内核配置。当前不处理 Secure Boot 签名。

在普通用户下准备已校验资产（会下载固定 NVIDIA 输入，不安装驱动）：

```bash
make assets
```

用 `uname -r` 查看当前运行的内核版本，在仓库根目录为该内核构建镜像：

```bash
sudo bash local/ubuntu-3090/build-image.sh \
  "$(uname -r)" "$HOME/.cache/gpu-unlock/assets"
```

生成 `/boot/initrd.img-$(uname -r)-server3090`（文件名中的版本为命令实际输出）。
若要为其他已安装内核构建，可从 `ls /lib/modules/` 查看版本并显式传入；
构建前安装对应的 `linux-headers-<版本>`。

构建器复制系统 initramfs 配置到临时目录，附加私有 hook；
删除专用镜像中的 GPU 绑定模块，加入自建模块、固定固件及早期 gate。
解包审计检查 gate 早于 udev、无竞争 binder、模块和固件哈希、无其他解锁加载引用。
失败不发布镜像；通过后在 /boot 同文件系统原子替换专用镜像。
日志 `/var/log/gpu-unlock-server3090/<kernel>/`。
构建前应审阅系统中的第三方 initramfs hook。

## 手动启动入口

### 1. 确定目标显卡

```bash
lspci -Dnn | grep -i NVIDIA
```

选择显卡的 PCI 地址，不要选择同卡的音频功能。下文地址均为示例。

### 2. 复制对应内核的普通菜单项

查看已生成的配置，找到与构建镜像相同内核版本的普通 Ubuntu `menuentry`：

```bash
sudo less /boot/grub/grub.cfg
```

例如构建版本是 `5.15.0-203-generic`，就复制使用该版本 `vmlinuz` 的菜单项，
从 `menuentry` 开始直到它对应的结束 `}`，包含其中的嵌套块，不复制外层 `submenu`。
不要直接编辑生成的 `grub.cfg`。

```bash
sudo cp -a /etc/grub.d/40_custom /etc/grub.d/40_custom.bak
sudoedit /etc/grub.d/40_custom
```

保留 `40_custom` 开头的脚本头和已有内容，将复制的完整菜单项追加到文件末尾。
在新增菜单项中只修改以下内容：

- 标题改为 `Ubuntu RTX 3090 unlock`，若有 `--id` 或 `$menuentry_id_option`，
  将后面的 ID 改为唯一值，例如 `rtx3090-unlock-5.15.0-203-generic`。
- `linux` 行保留内核路径、根分区及原有参数，在末尾追加目标参数。
- `initrd` 行只把普通 initrd 文件换成同版本的 `*-server3090` 镜像，保留其他微码文件和顺序。
- 保留原菜单项的 `search`、分区 UUID、`set root`、模块加载及其他启动逻辑。

例如 `/boot` 为独立分区时，相关两行的修改形式是（省略部分沿用原菜单项，不可原样粘贴）：

```text
linux /vmlinuz-5.15.0-203-generic ... gpu_unlock.targets=0000:01:00.0
initrd /initrd.img-5.15.0-203-generic-server3090
```

若原路径为 `/boot/vmlinuz-...` 和 `/boot/initrd.img-...`，保留 `/boot/` 前缀。
内核、专用镜像版本必须一致。

单卡参数：

```text
gpu_unlock.targets=0000:01:00.0
```

多卡参数（逗号分隔，不加空格）：

```text
gpu_unlock.targets=0000:01:00.0,0000:02:00.0,0000:03:00.0,0000:04:00.0
```

也可使用 `gpu_unlock.targets=all`，选择所有上游支持的目标，不局限于 3090。
同一内核镜像可通过参数选择不同目标，无需因地址变化重建。

### 3. 生成菜单并手动选择

```bash
sudo chmod +x /etc/grub.d/40_custom
sudo update-grub
sudo grub-script-check /boot/grub/grub.cfg
```

确认输出中没有错误，检查生成的配置中新增菜单项的内核、镜像路径及目标参数。
保留普通 Ubuntu 为默认项；重启时手动选择 `Ubuntu RTX 3090 unlock`。
若当前菜单被隐藏，可在 `/etc/default/grub` 中设置 `GRUB_TIMEOUT_STYLE=menu` 和
`GRUB_TIMEOUT=15`，保持 `GRUB_DEFAULT` 不变，再执行 `sudo update-grub`。
若使用 `GRUB_DEFAULT=saved` 并启用了 `GRUB_SAVEDEFAULT`，关闭自动保存选择，
以免手动选择解锁项后改变默认启动项。

此菜单使用固定版本路径；升级内核后，需重新构建专用镜像并更新菜单路径。

### 启动后验证

进入系统后检查四张卡的解锁日志和驱动状态：

```bash
sudo journalctl -b -k | grep 'gpu_unlock: unlocked'
nvidia-smi
```

确认目标 PCI 地址均有解锁记录，再按 `benchmarks/README.zh-CN.md` 运行数值和性能测试。

## 回退与清理

选择原来的普通启动项即可避免加载这个私有模块；固件状态仍可能需要完整断电恢复。
此实现不安装持久化钩子/全局模块，无 DKMS 卸载步骤。
停止使用对应 GRUB 项后，可人工核对并移除专用 `*-server3090` 镜像及专用日志；
不要删除普通 initrd、vmlinuz 或其他 DKMS 内容。

## 离线测试

```bash
python3 -m unittest discover -s local/ubuntu-3090/tests -v
```

测试使用临时数据和沙箱执行 gate（模拟模块加载器），不加载真实模块、不访问 GPU。

### Ubuntu 内建 VFIO 例外

5.15.0-203 内建 vfio-pci/core；它们不靠静态 GPU ID 自动接管，
允许这两个内建项，但仍删除镜像中的可加载 binder。启动参数中显式的
vfio-pci/pci-stub 配置会令 gate 跳过；已绑定设备仍由上游模块拒绝。
服务器当前未发现 VFIO 绑定设备或相关 initramfs/modprobe 配置。

## 四卡性能验证与复现

测试源码和脚本见 [`benchmarks/`](benchmarks/README.zh-CN.md)。
CUDA 12.2 / cuBLAS 120205，同一测试二进制 SHA-256：
`90138547034afd1f5599c81ac1ebf5f0019f43d5c60bb0b914bfb46b29c30f50`。
8192 阶 GEMM 各卡 5 组中位数的四卡平均值（TFLOPS，非并行总吞吐）：

| 模式 | 原厂 | 解锁后 | 变化 |
|---|---:|---:|---:|
| 严格 FP32 | 25.95 | 25.95 | 基本不变 |
| TF32 | 39.96 | 70.43 | +76.3% |
| FP16 输入 / FP32 累加 | 74.00 | 119.43 | +61.4% |
| BF16 输入 / FP32 累加 | 73.40 | 121.14 | +65.0% |
| FP16 输入 / FP16 累加 | 127.49 | 127.64 | +0.1% |

四卡测试正常退出，无 CUDA/cuBLAS 报错，测试后未发现 Xid。
256 阶全量检查及大矩阵抽样检查完成；本测试输入下 FP32 累加模式检查误差为零。
FP16 累加模式最大绝对误差 0.01953125，仅检查有限值、记录误差，不执行严格误差门限。
采样最高温度为 51/47/48/50°C，峰值功耗约 350W，未调整功耗上限。
