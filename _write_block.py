from pathlib import Path

block = r"""         <DIVTAG class="sidebar-section comment-section" :class="{ 'has-diff': hasEntityFieldDiff('append_comment') }">
           <h3 class="sidebar-title">评论记录</h3>
           <DIVTAG v-if="hasEntityFieldDiff('append_comment')" class="field-diff-panel field-diff-panel--stacked comment-diff-panel">
             <DIVTAG class="diff-header">
               <span class="diff-label">追加评论 · 修改预览</span>
               <DIVTAG class="diff-actions">
                 <button type="button" @click="applyFieldChange('append_comment')" class="btn-confirm" title="采纳">✓</button>
                 <button type="button" @click="cancelFieldChange('append_comment')" class="btn-cancel" title="取消">✗</button>
               </DIVTAG>
             </DIVTAG>
             <DIVTAG class="diff-content">
               <DIVTAG class="diff-row">
                 <span class="diff-tag new">新评论</span>
                 <span class="diff-value diff-value-multiline">{{ formatEntityDiffValue('append_comment', entityFieldDiff('append_comment')?.new) }}</span>
               </DIVTAG>
             </DIVTAG>
           </DIVTAG>
           <DIVTAG v-if="entityComments.length" class="comment-timeline">
             <DIVTAG v-for="c in entityComments" :key="c.id" class="comment-item">
               <DIVTAG class="comment-item-meta">
                 <span class="comment-author">{{ c.user_name || '—' }}</span>
                 <span class="comment-time">{{ formatCommentTime(c.created_at) }}</span>
                 <span v-if="c.source_message_id" class="comment-op-tag">来自对话操作</span>
               </DIVTAG>
               <DIVTAG class="comment-item-body" v-html="c.content"></DIVTAG>
             </DIVTAG>
           </DIVTAG>
           <DIVTAG v-else class="comment-empty">暂无评论</DIVTAG>
           <h4 class="comment-input-subtitle">输入评论</h4>
           <DIVTAG class="comment-input-container">
             <template v-if="!commentEditorActive">
               <textarea
                 class="comment-textarea-simple"
                 readonly
                 rows="3"
                 :value="commentDraftText"
                 placeholder="点击输入评论…"
                 @click="activateCommentEditor"
               />
               <DIVTAG class="comment-count">{{ commentDraftLength }} / 500</DIVTAG>
             </template>
             <template v-else>
               <RichTextHtmlEditor
                 v-model="commentDraft"
                 variant="compact"
                 placeholder="请输入评论"
                 class="rich-editor"
               />
               <DIVTAG class="comment-editor-actions">
                 <button type="button" class="comment-collapse-btn" @click="finishCommentEditor">收起</button>
                 <button
                   v-if="isEdit && normalizedBugId"
                   type="button"
                   class="comment-submit-btn"
                   :disabled="commentSubmitting || !commentDraftLength"
                   @click="submitCommentDraft"
                 >
                   发表评论
                 </button>
               </DIVTAG>
               <DIVTAG class="editor-count">{{ commentDraftLength }} / 500</DIVTAG>
             </template>
           </DIVTAG>
         </DIVTAG>
"""
block = block.replace("DIVTAG", "div")

vue = Path("electron-vue3/src/components/NewBug.vue")
text = vue.read_text(encoding="utf-8")
start = text.index("                  <!-- 输入评论：先只读预览，点击后再展开富文本 -->")
marker = "           </div>\n         </div>\n        </motion>"
if marker not in text:
    marker = "           </div>\n         </div>\n        </div>"
end = text.index(marker, start) + len(marker)
vue.write_text(text[:start] + block + text[end:], encoding="utf-8")
print("patched", start, end)
