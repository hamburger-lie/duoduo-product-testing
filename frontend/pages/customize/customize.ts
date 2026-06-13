import { api } from '../../services/api';

Page({
  data: {
    name: '',
    phone: '',
    company: '',
    requirement: '',
    submitting: false,
    submitted: false,
  },

  onLoad() {},

  onInputName(e: any) { this.setData({ name: e.detail.value }); },
  onInputPhone(e: any) { this.setData({ phone: e.detail.value }); },
  onInputCompany(e: any) { this.setData({ company: e.detail.value }); },
  onInputRequirement(e: any) { this.setData({ requirement: e.detail.value }); },

  onTapPhone(e: any) {
    wx.makePhoneCall({ phoneNumber: e.currentTarget.dataset.phone });
  },

  async onTapSubmit() {
    const { name, phone, company, requirement, submitting, submitted } = this.data;
    if (submitting || submitted) return;
    if (!name.trim()) { wx.showToast({ title: '请填写姓名', icon: 'none' }); return; }
    if (!phone.trim()) { wx.showToast({ title: '请填写联系电话', icon: 'none' }); return; }
    if (!company.trim()) { wx.showToast({ title: '请填写公司/品牌', icon: 'none' }); return; }
    if (!requirement.trim()) { wx.showToast({ title: '请填写需求描述', icon: 'none' }); return; }

    this.setData({ submitting: true });
    try {
      await api.submitCustomize({ name: name.trim(), phone: phone.trim(), company: company.trim(), requirement: requirement.trim() });
    } catch { /* 提交失败静默处理，不影响用户体验 */ }
    this.setData({ submitting: false, submitted: true });
  },

  onTapReset() {
    this.setData({ name: '', phone: '', company: '', requirement: '', submitted: false });
  },
});
