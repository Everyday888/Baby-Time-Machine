# 宝贝时光机

一个面向新手父母的温馨育儿记录项目，使用 Python、Flask、MySQL、HTML、CSS、JavaScript 构建，并接入 Web Awesome 组件库。

## 已实现功能

- 登录
- 注册
- 邮箱验证码忘记密码
- 家庭共享页面
- 宝宝展示页面
- 喂养、睡眠、排便、健康、里程碑记录
- 宝宝照片墙
- 身高体重头围成长曲线
- 疫苗提醒
- 管理员平台页面
- 家庭邀请码加入机制
- 管理员查看家庭详情
- 管理员停用用户
- 管理员筛选成长记录

## 技术栈

- Python 3.10
- Flask
- Flask-SQLAlchemy
- MySQL + PyMySQL
- HTML / CSS / JavaScript
- Web Awesome

## 目录说明

```text
app.py
requirements.txt
package.json
static/
  css/styles.css
  js/app.js
  js/webawesome.js
templates/
  base.html
  index.html
  dashboard.html
  admin.html
  auth/
    login.html
    register.html
    forgot_password.html
```

## 环境准备

1. 创建 MySQL 数据库。

```sql
CREATE DATABASE baby_time_machine CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

2. 配置环境变量。

可参考 [.env.example](.env.example)。至少需要：

```env
SECRET_KEY=replace-with-a-random-secret
DATABASE_URL=mysql+pymysql://root:your-password@localhost:3306/baby_time_machine?charset=utf8mb4
```

如果要启用真实邮箱验证码发送，再额外配置：

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-account@example.com
SMTP_PASSWORD=your-password
SMTP_FROM=your-account@example.com
```

3. 安装 Python 依赖。

```powershell
pip install -r requirements.txt
```

4. 安装前端依赖。

```powershell
npm install
```

说明：题目里给出的 `npm install "@webawesome/components"` 当前会返回 404。项目已改为安装官方已发布包 `@awesome.me/webawesome`，并通过本地 Flask 路由提供资源。

5. 初始化数据库表。

```powershell
flask --app app init-db
```

6. 启动项目。

```powershell
flask --app app run --debug
```

启动后访问：

- 首页: `http://127.0.0.1:5000/`
- 登录页: `http://127.0.0.1:5000/login`
- 注册页: `http://127.0.0.1:5000/register`

## 使用说明

### 注册

- 可以选择创建新家庭或加入已有家庭。
- 注册时必须选择角色，例如爸爸、妈妈、爷爷、奶奶、看护人或管理员。
- 同一个家庭的邀请码相同，加入后会共享同一家庭页面。

### 家庭空间

- 添加宝宝档案
- 查看宝宝年龄、生日、备注
- 记录喂养、睡眠、排便、健康和里程碑
- 添加宝宝照片墙
- 记录身高、体重、头围并生成成长曲线
- 添加疫苗提醒并显示即将到期状态
- 按时间轴查看最近家庭记录

### 管理员平台

- 统计家庭总数、成员总数、宝宝总数、事件总数
- 查看家庭邀请码和家庭数据概览
- 查看家庭详情、成员、照片、疫苗与最近事件
- 按家庭、事件类型、时间范围和关键词筛选记录
- 停用指定用户

## 本地演示说明

- 项目已支持 `.env` 读取本地 MySQL 连接配置。
- 如果未配置 SMTP，找回密码时会以开发模式直接显示验证码，便于本地演示。

## 后续可扩展方向

- 多宝宝切换视图
- 数据导出为 Excel 或 PDF
- 本地图片上传而不是仅保存图片地址
- 家庭邀请链接和邮件邀请
