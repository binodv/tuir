# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import docs
from .content import SubmissionContent
from .page import Page, PageController, logged_in
from .objects import Navigator, Command


class SubmissionController(PageController):
    character_map = {}


class SubmissionPage(Page):
    BANNER = docs.BANNER_SUBMISSION
    FOOTER = docs.FOOTER_SUBMISSION

    name = 'submission'

    def __init__(self, reddit, term, config, oauth, url=None, submission=None):
        super(SubmissionPage, self).__init__(reddit, term, config, oauth)

        self.controller = SubmissionController(self, keymap=config.keymap)

        if url:
            self.content = SubmissionContent.from_url(
                reddit, url, term.loader,
                max_comment_cols=config['max_comment_cols'])
        else:
            self.content = SubmissionContent(
                submission, term.loader,
                max_comment_cols=config['max_comment_cols'])

        # Start at the submission post, which is indexed as -1
        self.nav = Navigator(self.content.get, page_index=-1)

    def handle_selected_page(self):
        """
        Open the subscription page in a subwindow, but close the current page
        if any other type of page is selected.
        """
        if not self.selected_page:
            pass
        elif self.selected_page.name == 'subscription':
            # Launch page in a subwindow
            self.selected_page = self.selected_page.loop()
        elif self.selected_page.name in ('subreddit', 'submission', 'inbox'):
            # Replace the current page
            self.active = False
        else:
            raise RuntimeError(self.selected_page.name)

    def refresh_content(self, order=None, name=None):
        """
        Re-download comments and reset the page index
        """
        order = order or self.content.order
        url = name or self.content.name

        # Hack to allow an order specified in the name by prompt_subreddit() to
        # override the current default
        if order == 'ignore':
            order = None

        with self.term.loader('Refreshing page'):
            self.content = SubmissionContent.from_url(
                self.reddit, url, self.term.loader, order=order,
                max_comment_cols=self.config['max_comment_cols'])
        if not self.term.loader.exception:
            self.nav = Navigator(self.content.get, page_index=-1)

    @SubmissionController.register(Command('SORT_1'))
    def sort_content_hot(self):
        self.refresh_content(order='hot')

    @SubmissionController.register(Command('SORT_2'))
    def sort_content_top(self):
        self.refresh_content(order='top')

    @SubmissionController.register(Command('SORT_3'))
    def sort_content_rising(self):
        self.refresh_content(order='rising')

    @SubmissionController.register(Command('SORT_4'))
    def sort_content_new(self):
        self.refresh_content(order='new')

    @SubmissionController.register(Command('SORT_5'))
    def sort_content_controversial(self):
        self.refresh_content(order='controversial')

    @SubmissionController.register(Command('SUBMISSION_TOGGLE_COMMENT'))
    def toggle_comment(self):
        """
        Toggle the selected comment tree between visible and hidden
        """
        current_index = self.nav.absolute_index
        self.content.toggle(current_index)

        # This logic handles a display edge case after a comment toggle. We
        # want to make sure that when we re-draw the page, the cursor stays at
        # its current absolute position on the screen. In order to do this,
        # apply a fixed offset if, while inverted, we either try to hide the
        # bottom comment or toggle any of the middle comments.
        if self.nav.inverted:
            data = self.content.get(current_index)
            if data['hidden'] or self.nav.cursor_index != 0:
                window = self._subwindows[-1][0]
                n_rows, _ = window.getmaxyx()
                self.nav.flip(len(self._subwindows) - 1)
                self.nav.top_item_height = n_rows

    @SubmissionController.register(Command('SUBMISSION_EXIT'))
    def exit_submission(self):
        """
        Close the submission and return to the subreddit page
        """
        self.active = False

    @SubmissionController.register(Command('SUBMISSION_OPEN_IN_BROWSER'))
    def open_link(self):
        """
        Open the link contained in the selected item.

        If there is more than one link contained in the item, prompt the user
        to choose which link to open.
        """
        data = self.get_selected_item()
        if data['type'] == 'Submission':
            link = self.prompt_and_select_link()
            if link:
                self.config.history.add(link)
                self.term.open_link(link)
        elif data['type'] == 'Comment':
            link = self.prompt_and_select_link()
            if link:
                self.term.open_link(link)
        else:
            self.term.flash()

    @SubmissionController.register(Command('SUBMISSION_OPEN_IN_PAGER'))
    def open_pager(self):
        """
        Open the selected item with the system's pager
        """
        n_rows, n_cols = self.term.stdscr.getmaxyx()

        if self.config['max_pager_cols'] is not None:
            n_cols = min(n_cols, self.config['max_pager_cols'])

        data = self.get_selected_item()
        if data['type'] == 'Submission':
            text = '\n\n'.join((data['permalink'], data['text']))
            self.term.open_pager(text, wrap=n_cols)
        elif data['type'] == 'Comment':
            text = '\n\n'.join((data['permalink'], data['body']))
            self.term.open_pager(text, wrap=n_cols)
        else:
            self.term.flash()

    @SubmissionController.register(Command('SUBMISSION_POST'))
    @logged_in
    def add_comment(self):
        """
        Submit a reply to the selected item.
        """
        self.reply()

    @SubmissionController.register(Command('DELETE'))
    @logged_in
    def delete_comment(self):
        """
        Delete the selected comment
        """
        if self.get_selected_item()['type'] == 'Comment':
            self.delete_item()
        else:
            self.term.flash()

    @SubmissionController.register(Command('SUBMISSION_OPEN_IN_URLVIEWER'))
    def comment_urlview(self):
        """
        Open the selected comment with the URL viewer
        """
        data = self.get_selected_item()
        comment = data.get('body') or data.get('text') or data.get('url_full')
        if comment:
            self.term.open_urlview(comment)
        else:
            self.term.flash()

    @SubmissionController.register(Command('SUBMISSION_GOTO_PARENT'))
    def move_parent_up(self):
        """
        Move the cursor up to the comment's parent. If the comment is
        top-level, jump to the previous top-level comment.
        """
        cursor = self.nav.absolute_index
        if cursor > 0:
            level = max(self.content.get(cursor)['level'], 1)
            while self.content.get(cursor - 1)['level'] >= level:
                self._move_cursor(-1)
                cursor -= 1
            self._move_cursor(-1)
        else:
            self.term.flash()

        self.clear_input_queue()

    @SubmissionController.register(Command('SUBMISSION_GOTO_SIBLING'))
    def move_sibling_next(self):
        """
        Jump to the next comment that's at the same level as the selected
        comment and shares the same parent.
        """
        cursor = self.nav.absolute_index
        if cursor >= 0:
            level = self.content.get(cursor)['level']
            try:
                move = 1
                while self.content.get(cursor + move)['level'] > level:
                    move += 1
            except IndexError:
                self.term.flash()
            else:
                if self.content.get(cursor + move)['level'] == level:
                    for _ in range(move):
                        self._move_cursor(1)
                else:
                    self.term.flash()
        else:
            self.term.flash()

        self.clear_input_queue()

    def _draw_item(self, win, data, inverted):

        if data['type'] == 'MoreComments':
            return self._draw_more_comments(win, data)
        elif data['type'] == 'HiddenComment':
            return self._draw_more_comments(win, data)
        elif data['type'] == 'Comment':
            return self._draw_comment(win, data, inverted)
        else:
            return self._draw_submission(win, data)

    def _draw_comment(self, win, data, inverted):

        n_rows, n_cols = win.getmaxyx()
        n_cols -= 1

        # Handle the case where the window is not large enough to fit the text.
        valid_rows = range(0, n_rows)
        offset = 0 if not inverted else -(data['n_rows'] - n_rows)

        # If there isn't enough space to fit the comment body on the screen,
        # replace the last line with a notification.
        split_body = data['split_body']
        if data['n_rows'] > n_rows:
            # Only when there is a single comment on the page and not inverted
            if not inverted and len(self._subwindows) == 1:
                cutoff = data['n_rows'] - n_rows + 1
                split_body = split_body[:-cutoff]
                split_body.append('(Not enough space to display)')

        row = offset
        if row in valid_rows:
            if data['is_author']:
                attr = self.term.attr('CommentAuthorSelf')
                text = '{author} [S]'.format(**data)
            else:
                attr = self.term.attr('CommentAuthor')
                text = '{author}'.format(**data)
            self.term.add_line(win, text, row, 1, attr)

            if data['flair']:
                attr = self.term.attr('UserFlair')
                self.term.add_space(win)
                self.term.add_line(win, '{flair}'.format(**data), attr=attr)

            arrow, attr = self.term.get_arrow(data['likes'])
            self.term.add_space(win)
            self.term.add_line(win, arrow, attr=attr)

            attr = self.term.attr('Score')
            self.term.add_space(win)
            self.term.add_line(win, '{score} pts'.format(**data), attr=attr)

            attr = self.term.attr('Created')
            self.term.add_space(win)
            self.term.add_line(win, '{created}{edited}'.format(**data),
                               attr=attr)

            if data['gold']:
                attr = self.term.attr('Gold')
                self.term.add_space(win)
                count = 'x{}'.format(data['gold']) if data['gold'] > 1 else ''
                text = self.term.gilded + count
                self.term.add_line(win, text, attr=attr)

            if data['stickied']:
                attr = self.term.attr('Stickied')
                self.term.add_space(win)
                self.term.add_line(win, '[stickied]', attr=attr)

            if data['saved']:
                attr = self.term.attr('Saved')
                self.term.add_space(win)
                self.term.add_line(win, '[saved]', attr=attr)

        for row, text in enumerate(split_body, start=offset + 1):
            attr = self.term.attr('CommentText')
            if row in valid_rows:
                self.term.add_line(win, text, row, 1, attr=attr)

        # curses.vline() doesn't support custom colors so need to build the
        # cursor bar on the left of the comment one character at a time
        index = data['level'] % len(self.term.theme.CURSOR_BARS)
        attr = self.term.attr(self.term.theme.CURSOR_BARS[index])
        for y in range(n_rows):
            self.term.addch(win, y, 0, self.term.vline, attr)

    def _draw_more_comments(self, win, data):

        n_rows, n_cols = win.getmaxyx()
        n_cols -= 1

        attr = self.term.attr('HiddenCommentText')
        self.term.add_line(win, '{body}'.format(**data), 0, 1, attr=attr)

        attr = self.term.attr('HiddenCommentExpand')
        self.term.add_space(win)
        self.term.add_line(win, '[{count}]'.format(**data), attr=attr)

        index = data['level'] % len(self.term.theme.CURSOR_BARS)
        attr = self.term.attr(self.term.theme.CURSOR_BARS[index])
        self.term.addch(win, 0, 0, self.term.vline, attr)

    def _draw_submission(self, win, data):

        n_rows, n_cols = win.getmaxyx()
        n_cols -= 3  # one for each side of the border + one for offset

        attr = self.term.attr('SubmissionTitle')
        for row, text in enumerate(data['split_title'], start=1):
            self.term.add_line(win, text, row, 1, attr)

        row = len(data['split_title']) + 1
        attr = self.term.attr('SubmissionAuthor')
        self.term.add_line(win, '{author}'.format(**data), row, 1, attr)

        if data['flair']:
            attr = self.term.attr('SubmissionFlair')
            self.term.add_space(win)
            self.term.add_line(win, '{flair}'.format(**data), attr=attr)

        attr = self.term.attr('SubmissionSubreddit')
        self.term.add_space(win)
        self.term.add_line(win, '/r/{subreddit}'.format(**data), attr=attr)

        attr = self.term.attr('Created')
        self.term.add_space(win)
        self.term.add_line(win, '{created_long}{edited_long}'.format(**data),
                           attr=attr)

        row = len(data['split_title']) + 2
        if data['url_full'] in self.config.history:
            attr = self.term.attr('LinkSeen')
        else:
            attr = self.term.attr('Link')
        self.term.add_line(win, '{url}'.format(**data), row, 1, attr)

        offset = len(data['split_title']) + 3

        # Cut off text if there is not enough room to display the whole post
        split_text = data['split_text']
        if data['n_rows'] > n_rows:
            cutoff = data['n_rows'] - n_rows + 1
            split_text = split_text[:-cutoff]
            split_text.append('(Not enough space to display)')

        attr = self.term.attr('SubmissionText')
        for row, text in enumerate(split_text, start=offset):
            self.term.add_line(win, text, row, 1, attr=attr)

        row = len(data['split_title']) + len(split_text) + 3
        attr = self.term.attr('Score')
        self.term.add_line(win, '{score} pts'.format(**data), row, 1, attr=attr)

        arrow, attr = self.term.get_arrow(data['likes'])
        self.term.add_space(win)
        self.term.add_line(win, arrow, attr=attr)

        attr = self.term.attr('CommentCount')
        self.term.add_space(win)
        self.term.add_line(win, '{comments} comments'.format(**data), attr=attr)

        if data['gold']:
            attr = self.term.attr('Gold')
            self.term.add_space(win)
            count = 'x{}'.format(data['gold']) if data['gold'] > 1 else ''
            text = self.term.gilded + count
            self.term.add_line(win, text, attr=attr)

        if data['nsfw']:
            attr = self.term.attr('NSFW')
            self.term.add_space(win)
            self.term.add_line(win, 'NSFW', attr=attr)

        if data['saved']:
            attr = self.term.attr('Saved')
            self.term.add_space(win)
            self.term.add_line(win, '[saved]', attr=attr)

        win.border()
