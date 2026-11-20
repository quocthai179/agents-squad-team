# Bộ ảnh marketing Agents Squad Team

Bộ ảnh dành cho repository `quocthai179/agents-squad-team`, dựa trên 16 file agent và 14 file command ở nhánh mặc định tại thời điểm chuẩn bị 20/11/2026.

Phong cách: nền navy, kính mờ 3D, điểm nhấn tím và cyan. Ảnh dùng chữ tiếng Anh để chia sẻ tới cộng đồng developer; tài liệu hướng dẫn giữ tiếng Việt.

## Các file

| File trong `assets/marketing/` | Mục đích | Kích thước |
|---|---|---|
| `specialists-shared-context.png` | Giới thiệu đội agent và ngữ cảnh chung | 1672 × 941 px |
| `hero-banner.png` | Banner đầu README | 1920 × 819 px |
| `feature-workflow.png` | Sơ đồ workflow feature | 2400 × 1740 px |
| `social-preview.png` | Ảnh bài đăng / GitHub social preview | 1732 × 908 px |
| `feature-workflow.svg` | Bản vector chỉnh sửa được | 1600 × 1160 viewBox |

`feature-workflow.svg` là bản vector có thể chỉnh sửa và giữ chữ sắc nét. Bản PNG giúp nhúng và chia sẻ thuận tiện. Ba ảnh minh họa được tạo bằng công cụ tạo ảnh tích hợp; sơ đồ được dựng từ SVG rồi render để giữ chính xác thứ tự và tên vai trò. Các prompt gốc nằm trong `prompts.json`.

## Thêm vào repository

1. Copy `assets/marketing/` vào repository.
2. Dùng bản `README.md` trong gói nếu README hiện tại vẫn trùng bản gốc, hoặc chèn các đoạn dưới đây vào README hiện tại để giữ các chỉnh sửa mới của bạn.
3. Copy `docs/marketing/` nếu muốn lưu hướng dẫn và prompt cùng source.

Sau tiêu đề chính:

```markdown
![Agents Squad Team — 16 agent, 14 workflow cho Claude Code](assets/marketing/hero-banner.png)
```

Trong phần giới thiệu đội hình:

```markdown
![Các chuyên gia chia sẻ ngữ cảnh và bàn giao qua .squad](assets/marketing/specialists-shared-context.png)
```

Trước bảng lệnh workflow:

```markdown
![Quy trình feature của Agents Squad Team](assets/marketing/feature-workflow.png)
```

Các đường dẫn trên tính từ README ở thư mục gốc repository. Không cần dịch vụ lưu ảnh bên ngoài.

## Ảnh chia sẻ mạng xã hội

`social-preview.png` dùng cho bài đăng giới thiệu source hoặc tải lên phần **Settings → General → Social preview** của GitHub. Việc thêm file vào source chưa tự thay đổi ảnh social preview của GitHub.

Gợi ý caption:

> Một prompt, một đội AI phối hợp ngay trong Claude Code. Agents Squad Team gồm 16 agent chuyên biệt và 14 lệnh workflow, từ phân tích yêu cầu, thiết kế, lập trình đến test, review và xử lý sự cố. Chia sẻ artifact qua `.squad/`, có bước bàn giao rõ ràng. Source mở, giấy phép MIT.
>
> https://github.com/quocthai179/agents-squad-team

## Nội dung và bảo trì

- Khối kính trong ảnh là minh họa ý tưởng, không phải ảnh chụp giao diện hay danh sách đầy đủ các agent.
- Workflow đã đối chiếu với `plugins/dev-squad/commands/feature.md`. Review và security có thể chạy song song khi phù hợp; lỗi blocking cần được sửa rồi review lại. Thay đổi DB có thêm database-engineer.
- Không đưa số liệu tăng năng suất, tiết kiệm chi phí hay kết quả benchmark chưa được chứng minh vào ảnh.
- Khi thay đổi số agent hoặc workflow, cần cập nhật các số 16/14 trong ảnh và nội dung mô tả.
- Bộ ảnh gồm tài nguyên marketing và tài liệu; ảnh social preview của repository được cấu hình riêng trong Settings của GitHub.
