#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Tencent Inc.
# Author: Xuemin Zhao (xueminzhao@tencent.com)

import os, sys, copy
import re, json, logging


SCHEMAS = {
    'music.play' : set(['song', 'singer', 'theme', 'style', 
                        'age', 'toplist', 'emotion', 'language', 
                        'instrument', 'scene']),
    'music.pause' : set([]),
    'music.next' : set([]),
    'music.prev' : set([]),
    'navigation.navigation' : set(['destination', 'custom_destination', 'origin']),
    'navigation.cancel_navigation' : set([]),
    'navigation.start_navigation' : set([]),
    'navigation.open' : set([]),
    'phone_call.make_a_phone_call' : set(['phone_num', 'contact_name']),
    'phone_call.cancel' : set([]),
    'OTHERS' : set([]),
}

TEAMS = [
#    "AlphaGOU",
#    "CVTE_SLU",
#    "DeepIntell",
#    "DLUFL_SLU",
#    "FAQRobot-wds",
#    "HappyRogue",
#    "HCCL",
#    "ISCLAB",
#    "laiye_rocket",
#    "Learner",
#    "orion_nlp",
#    "rax",
#    "scau_SLU",
#    "SLU-encoder",
#    "SMIPG",
#    "Team_4",
    'Golden',
]


PATTERN = re.compile('<(.+?)>')
def parse_seq_tagged_text(s, enames=None):
    ''' fmt: <singer>华仔</singer>和<singer>阿sa</singer>的歌
        ret: bool, original_text, dict<name, [(offset, value)]>
             True, u'华仔和阿sa的歌', {'singer': [(0, u'华仔'), (3, u'阿sa')]}
    '''

    ms = list(PATTERN.finditer(s))
    ok = len(ms) % 2 == 0
    for i in range(len(ms) / 2):
        ok = ok and '/' + ms[2 * i].group(1) == ms[2 * i + 1].group(1)
    if not ok:
        return False, u'', {}, u''

    es = {}
    offset = 0
    src, s2 = u'', u''
    for i in range(len(ms) / 2):
        mb, me = ms[2 * i], ms[2 * i + 1]
        src += s[offset : mb.start()]
        s2 += s[offset : mb.start()]
        val = s[mb.end(): me.start()]
        name = ms[2 * i].group(1)

        if name not in es:
            es[name] = []
        es[name].append((len(src), val))

        val_fds = val.split('||')
        assert len(val_fds) <= 2

        src += val_fds[0]
        if enames is None:
            s2 += (u'<%s>%s</%s>' % (name, val, name))
        elif name in enames:
            s2 += (u'<%s>%s</%s>' % (name, val, name))
        else:
            s2 += val_fds[0]
        offset = me.end()
    src += s[offset:]
    s2 += s[offset:]
    return True, src, es, s2

def json_dumps(j):
    return json.dumps(j, ensure_ascii=False)

def load_sessions(fname, num_fds=4):
    with open(fname) as f:
        ses, sess = [], []
        for line in f:
            # print >> sys.stderr, line.strip()
            line = line.strip().decode('utf-8')
            if len(line) == 0 and len(ses) > 0:
                sess.append(ses)
                ses = []
            elif len(line) > 0:
                fds = line.split('\t')
                assert len(fds) == num_fds
                ses.append([fd.strip() for fd in fds])
        if len(ses) > 0:
            sess.append(ses)
    return sess

def load_dict(filename):
    with open(filename) as f:
        d = set()
        for line in f:
            try:
                line = line.strip().decode('utf-8')
                if line:
                    d.add(line)
            except:
                logging.error('codec error, file: %s, line: %s', filename, line)
    return d

def _divide(a, b):
    assert (a == 0 and b == 0) or b != 0
    if b != 0:
        return a * 1.0 / b
    if a == 0 and b == 0:
        return 0

def _yellow(s):
    return '\033[1;33;40m%s\033[0m' % s

def _green(s):
    return '\033[1;32;40m%s\033[0m' % s

def _red(s):
    return '\033[1;31;40m%s\033[0m' % s

def _parse(u, only_intent):
    # if u[2] not in SCHEMAS:
    #     print >> sys.stderr, _yellow('\t'.join(u).encode('utf-8'))
    intent = u[2] if u[2] in SCHEMAS else 'OTHERS'
    if only_intent:
        return intent

    _, _, slots, _ = parse_seq_tagged_text(u[3])
    slots2 = []
    v = []
    for k, v in slots.items():
        if k in SCHEMAS[intent]:  # filter slots using schema
            v2 = []
            for e in v:
                e_fds = e[1].split('||')  # slot value correction
                e_val = e_fds[-1]
                if e_val not in v2:  # de-duplicate slot value
                    v2.append(e_val)
            v2.sort()
            slots2.append('%s=%s' % (k, ','.join(v2)))
    slots2.sort()
    semantic = '%s@%s' % (intent, '&'.join(slots2))
    return semantic


def _eval_intent(golden_sess, pred_sess):
    assert len(golden_sess) == len(pred_sess)

    stat = {k : {'tp' : 0, 'fp' : 0, 'fn' : 0} for k in SCHEMAS.keys()}
    for sid in range(len(golden_sess)):
        golden_ses, pred_ses = golden_sess[sid], pred_sess[sid]
        assert len(golden_ses) == len(pred_ses)
        for uid in range(len(golden_ses)):
            golden_u, pred_u = golden_ses[uid], pred_ses[uid]
            assert golden_u[0] == pred_u[0]

            golden_intent = _parse(golden_u, True)
            pred_intent = _parse(pred_u, True)
            if golden_intent == pred_intent:
                stat[golden_intent]['tp'] += 1
            elif golden_intent != pred_intent:
                stat[golden_intent]['fn'] += 1
                stat[pred_intent]['fp'] += 1

    for k, v in stat.items():
        if v['tp'] + v['fp'] == 0 or v['tp'] + v['fn'] == 0:
            print >> sys.stderr, _yellow(   \
                'WARNING: intent=%s, tp=%s, fp=%s, fn=%s\033[0m' \
                % (k, v['tp'], v['fp'], v['fn']))
        v['P'] = _divide(v['tp'], v['tp'] + v['fp'])
        v['R'] = _divide(v['tp'], v['tp'] + v['fn'])
        v['F1'] = _divide(2 * v['P'] * v['R'], v['P'] + v['R'])

    print >> sys.stderr, stat
    n = len(stat) - 1
    Pmacro = sum(v['P'] for k, v in stat.items() if k != 'OTHERS') / n
    Rmacro = sum(v['R'] for k, v in stat.items() if k != 'OTHERS') / n
    F1macro = _divide(2 * Pmacro * Rmacro, Pmacro + Rmacro)
    print >> sys.stderr, 'Pmacro=%s, Rmacro=%s, F1macro=%s'  \
        % (Pmacro, Rmacro, F1macro)
    return F1macro

def _eval_intent_slot(golden_sess, pred_sess):
    assert len(golden_sess) == len(pred_sess)

    total_cnt, correct_cnt = 0, 0
    for sid in range(len(golden_sess)):
        golden_ses, pred_ses = golden_sess[sid], pred_sess[sid]
        assert len(golden_ses) == len(pred_ses)
        for uid in range(len(golden_ses)):
            golden_u, pred_u = golden_ses[uid], pred_ses[uid]
            assert golden_u[0] == pred_u[0]
            # assert pred_u[2] in SCHEMAS

            golden_semantic = _parse(golden_u, False)
            pred_semantic = _parse(pred_u, False)
            total_cnt += 1
            if golden_semantic == pred_semantic:
                correct_cnt += 1

            if 0:
                print >> sys.stderr, ('\t'.join(pred_u)).encode('utf-8')
                print >> sys.stderr, pred_semantic.encode('utf-8')

    P = _divide(correct_cnt, total_cnt)
    print >> sys.stderr, 'correct #=%s, total #=%s, P=%s'  \
        % (correct_cnt, total_cnt, P)
    return P


def main(argv):
    if len(argv) != 1:
        print >> sys.stderr, 'python nlpcc_eval.py DIR'
        return -1
    d = argv[0]

    golden_sess = load_sessions(d + '/corpus.test.txt', 4)
    for team in TEAMS:
        print >> sys.stderr, _green('[Team: %s]' % team)
        collector = [team]

        # subtask 2
        subtask = 2
        print >> sys.stderr, 'subtask %s' % subtask

        max_res2 = -1
        for t in [1, 2, 3]:
            path = '%s/%s/task4-subtask%s-result%s.txt'  \
                % (d, team, subtask, t)
            if not os.path.exists(path):
                continue

            print >> sys.stderr, 'result %s:' % t,
            pred_sess = load_sessions(path, 3)
            res = _eval_intent(golden_sess, pred_sess)
            if res > max_res2:
                max_res2 = res
            if len(collector) == 1:
                collector.append([res])
            else:
                collector[1].append(res)
        collector.append(max_res2)

        # subtask 4
        subtask = 4
        print >> sys.stderr, 'subtask %s' % subtask

        max_res4 = -1
        for t in [1, 2, 3]:
            path = '%s/%s/task4-subtask%s-result%s.txt'  \
                % (d, team, subtask, t)
            if not os.path.exists(path):
                continue

            print >> sys.stderr, 'result %s:' % t,
            pred_sess = load_sessions(path, 4)
            res = _eval_intent_slot(golden_sess, pred_sess)
            if res > max_res4:
                max_res4 = res
            if len(collector) == 3:
                collector.append([res])
            else:
                collector[3].append(res)
        collector.append(max_res4)

        print >> sys.stderr, _red("Final: subtask2=%s, subtask4=%s"  \
            % (max_res2, max_res4))

        collector[1] = '/'.join('%.4f' % e for e in collector[1])
        collector[3] = '/'.join('%.4f' % e for e in collector[3])
        print >> sys.stdout, '\t'.join(str(e) for e in collector)

if __name__ == '__main__':
    main(sys.argv[1:])
