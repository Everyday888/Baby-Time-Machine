/**
 * Baby Time Machine - 二维码分享工具
 * 使用 qrcode.js 库，支持动态生成和下载二维码
 */

class QRCodeGenerator {
  constructor(options = {}) {
    this.apiUrl = options.apiUrl || '/api/qrcode';
    this.defaultSize = options.size || 300;
  }

  renderWithQrCreator(container, value) {
    if (!window.QrCreator || typeof window.QrCreator.render !== 'function') {
      return null;
    }

    const canvas = document.createElement('canvas');
    canvas.width = this.defaultSize;
    canvas.height = this.defaultSize;
    canvas.className = 'qrcode-image';

    window.QrCreator.render(
      {
        text: value,
        radius: 0.22,
        ecLevel: 'H',
        fill: '#222222',
        background: '#ffffff',
        size: this.defaultSize,
      },
      canvas
    );

    container.innerHTML = '';
    container.appendChild(canvas);
    return canvas.toDataURL('image/png');
  }

  /**
   * 生成二维码并将其显示在指定容器中
   * @param {string} containerId - 容器元素 ID
   * @param {string} value - 要编码的值
   * @param {string} type - 二维码类型 (invite/share)
   */
  async renderQRCode(containerId, value, type = 'invite') {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error(`Container ${containerId} not found`);
      return;
    }

    try {
      // 优先使用前端本地渲染，避免后端依赖缺失导致失败
      const localDataUrl = this.renderWithQrCreator(container, value);
      if (localDataUrl) {
        return localDataUrl;
      }

      // 调用后端 API 生成二维码
      const response = await fetch(this.apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: type,
          value: value,
        }),
      });

      if (!response.ok) {
        let errorMessage = 'Failed to generate QR code';
        try {
          const errorPayload = await response.json();
          if (errorPayload && errorPayload.error) {
            errorMessage = errorPayload.error;
          }
        } catch (e) {
          // 忽略 JSON 解析失败，保留默认错误文案
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();

      // 清空容器
      container.innerHTML = '';

      // 创建图像元素
      const img = document.createElement('img');
      img.src = data.qrcode;
      img.alt = `${type} QR Code`;
      img.className = 'qrcode-image';
      img.style.maxWidth = this.defaultSize + 'px';
      img.style.height = 'auto';

      container.appendChild(img);

      // 返回 base64 用于下载
      return data.qrcode;
    } catch (error) {
      console.error('Error generating QR code:', error);
      container.innerHTML = '<p class="error">生成二维码失败，请重试</p>';
      return null;
    }
  }

  /**
   * 下载二维码
   * @param {string} base64Data - base64 编码的图像数据
   * @param {string} filename - 文件名
   */
  downloadQRCode(base64Data, filename = 'qrcode.png') {
    const link = document.createElement('a');
    link.href = base64Data;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  /**
   * 获取邀请码的分享文本
   * @param {string} code - 邀请码
   * @param {string} familyName - 家庭名称
   */
  getShareText(code, familyName = '我的家庭') {
    return `我在使用「宝贝时光机」记录宝宝的成长！邀请你加入 ${familyName}，一起见证美好时刻。\n邀请码：${code}`;
  }

  /**
   * 将二维码复制到剪贴板（仅限 HTTPS）
   * @param {HTMLCanvasElement|HTMLImageElement} element - 二维码元素
   */
  async copyQRCodeToClipboard(element) {
    if (!element) {
      console.error('Element not found');
      return false;
    }

    try {
      // 如果是图像，转换为 canvas
      let canvas = element;
      if (element.tagName === 'IMG') {
        canvas = await this.imageToCanvas(element);
      }

      // 使用 Canvas.toBlob() 复制到剪贴板
      canvas.toBlob(async (blob) => {
        try {
          await navigator.clipboard.write([
            new ClipboardItem({ 'image/png': blob }),
          ]);
          console.log('QR code copied to clipboard');
          return true;
        } catch (err) {
          console.error('Failed to copy to clipboard:', err);
          return false;
        }
      });
    } catch (error) {
      console.error('Error copying QR code:', error);
      return false;
    }
  }

  /**
   * 图像转 Canvas
   * @param {HTMLImageElement} img - 图像元素
   */
  imageToCanvas(img) {
    return new Promise((resolve) => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      resolve(canvas);
    });
  }

  /**
   * 生成微信分享卡片（供微信营销）
   * @param {string} code - 邀请码
   * @param {string} familyName - 家庭名称
   */
  getWeChatShare(code, familyName = '我的家庭') {
    const text = this.getShareText(code, familyName);
    return {
      title: '加入宝贝时光机',
      desc: `邀请码：${code}`,
      link: `https://baby-time-machine.com/join?code=${code}`,
      imgUrl: 'https://baby-time-machine.com/static/icon.png',
      type: 'link',
      dataUrl: '',
      trigger: function (check) {
        if (!check) {
          alert('请先分享到微信朋友圈');
        }
      },
      success: function () {
        alert('分享成功！');
      },
      cancel: function () {
        alert('已取消分享');
      },
      fail: function (res) {
        alert('分享失败：' + JSON.stringify(res));
      },
      complete: function () {
        // 完成
      },
    };
  }
}

// 全局导出
window.QRCodeGenerator = QRCodeGenerator;

// 自动初始化（可选）
document.addEventListener('DOMContentLoaded', function () {
  // 查找所有带 data-qrcode 属性的容器并自动生成
  const qrcodeContainers = document.querySelectorAll('[data-qrcode]');
  if (qrcodeContainers.length > 0) {
    const generator = new QRCodeGenerator();
    qrcodeContainers.forEach((container) => {
      const value = container.dataset.qrcodeValue || container.dataset.qrcode;
      const type = container.dataset.qrcodeType || 'invite';
      const id = container.id || `qrcode-${Math.random().toString(36).substr(2, 9)}`;
      container.id = id;
      generator.renderQRCode(id, value, type);
    });
  }
});
